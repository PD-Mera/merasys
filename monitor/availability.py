"""Confirmed availability intervals. No per-poll history rows or inferred backfill."""
from datetime import datetime, time, timedelta

from sqlalchemy import or_, select

from .db import AvailabilityCursor, AvailabilityDaily, AvailabilityInterval, Target, now

STATES = ("UP", "DOWN", "UNKNOWN", "DISABLED", "NO_DATA")


def iso(value):
    return value.isoformat() + "Z" if value else None


def _cursor(session, target, stamp):
    cursor = session.scalar(select(AvailabilityCursor).where(AvailabilityCursor.target_id == target.id).with_for_update())
    if cursor is None:
        state = "UNKNOWN" if target.enabled else "DISABLED"
        interval = AvailabilityInterval(target_id=target.id, state=state, started_at=stamp, reason="Bắt đầu ghi lịch sử" if target.enabled else "Đã tắt giám sát")
        session.add(interval)
        session.flush()
        cursor = AvailabilityCursor(target_id=target.id, state=state, started_at=stamp, recorded_since=stamp, interval_id=interval.id)
        session.add(cursor)
        session.flush()
    return cursor


def _transition(session, cursor, state, stamp, reason):
    if cursor.state == state:
        return
    stamp = max(stamp, cursor.started_at)
    interval = session.get(AvailabilityInterval, cursor.interval_id)
    if interval is not None:
        interval.ended_at = stamp
    next_interval = AvailabilityInterval(target_id=cursor.target_id, state=state, started_at=stamp, reason=reason[:1600])
    session.add(next_interval)
    session.flush()
    cursor.state, cursor.started_at, cursor.interval_id = state, stamp, next_interval.id


def _expire(session, cursor, stamp, stale_seconds):
    if cursor.state in {"UP", "DOWN"} and cursor.last_observed_at:
        deadline = cursor.last_observed_at + timedelta(seconds=stale_seconds)
        if stamp >= deadline:
            _transition(session, cursor, "UNKNOWN", deadline, "Dữ liệu agent quá hạn; không suy diễn khoảng mất dữ liệu là UP hoặc DOWN")


def configure(session, target, stamp=None, stale_seconds=180):
    stamp = stamp or now()
    # The caller locks target rows first, so cursor creation cannot race ingestion.
    cursor = _cursor(session, target, stamp)
    _expire(session, cursor, stamp, stale_seconds)
    if not target.enabled:
        _transition(session, cursor, "DISABLED", stamp, "Đã tắt hoặc xóa khai báo giám sát")
        cursor.last_observed_at = None
    elif cursor.state == "DISABLED":
        _transition(session, cursor, "UNKNOWN", stamp, "Bật giám sát; đang chờ đủ mẫu xác nhận")
        cursor.last_observed_at = None
    return cursor


def observe(session, target, stamp, failure_threshold, recovery_threshold, stale_seconds):
    cursor = configure(session, target, stamp, stale_seconds)
    if not target.enabled:
        return
    state = cursor.state
    if target.status == "UNKNOWN":
        state = "UNKNOWN"
    elif target.status == "DOWN" and target.failures >= failure_threshold:
        state = "DOWN"
    elif target.status == "UP" and target.successes >= recovery_threshold:
        state = "UP"
    # Pending failure/recovery samples keep the last confirmed state.
    reason = "Đã đủ mẫu xác nhận hoạt động" if state == "UP" else target.reason
    _transition(session, cursor, state, stamp, reason)
    cursor.last_observed_at = stamp


def expire_all(session, stamp, stale_seconds):
    cursors = session.scalars(select(AvailabilityCursor).where(AvailabilityCursor.state.in_(["UP", "DOWN"])).order_by(AvailabilityCursor.target_id).with_for_update())
    for cursor in cursors:
        _expire(session, cursor, stamp, stale_seconds)


def initialize_history(session, stale_seconds=180):
    stamp = now()
    for target in session.scalars(select(Target).where(Target.archived.is_(False)).order_by(Target.id).with_for_update()):
        configure(session, target, stamp, stale_seconds)


def report(session, target_id, period, stale_seconds):
    hours, bucket_count = {"24h": (24, 24), "7d": (168, 28), "30d": (720, 30)}[period]
    end = now()
    start = end - timedelta(hours=hours)
    cursor = session.get(AvailabilityCursor, target_id)
    intervals = list(session.scalars(select(AvailabilityInterval).where(
        AvailabilityInterval.target_id == target_id, AvailabilityInterval.started_at < end,
        or_(AvailabilityInterval.ended_at.is_(None), AvailabilityInterval.ended_at > start),
    ).order_by(AvailabilityInterval.started_at, AvailabilityInterval.id)))
    segments = []
    for interval in intervals:
        left, right = max(start, interval.started_at), min(end, interval.ended_at or end)
        if right <= left:
            continue
        # Read-time projection remains accurate even while the alert worker is offline.
        if interval.ended_at is None and interval.state in {"UP", "DOWN"} and cursor and cursor.last_observed_at:
            deadline = cursor.last_observed_at + timedelta(seconds=stale_seconds)
            cutoff = max(left, min(right, deadline))
            if cutoff > left:
                segments.append((left, cutoff, interval.state, interval.reason))
            if right > cutoff:
                segments.append((cutoff, right, "UNKNOWN", "Dữ liệu agent quá hạn"))
        else:
            segments.append((left, right, interval.state, interval.reason))
    totals = {state: 0.0 for state in STATES}
    buckets = []
    width = (end - start) / bucket_count
    for index in range(bucket_count):
        left, right = start + width * index, start + width * (index + 1)
        seconds = {state: 0.0 for state in STATES}
        for a, b, state, _ in segments:
            overlap = (min(b, right) - max(a, left)).total_seconds()
            if overlap > 0:
                seconds[state] += overlap
        seconds["NO_DATA"] = max(0.0, (right - left).total_seconds() - sum(seconds.values()))
        for state in STATES:
            totals[state] += seconds[state]
        color = next((state for state in ("DOWN", "UNKNOWN", "UP", "DISABLED") if seconds[state] > 0), "NO_DATA")
        buckets.append({"start": iso(left), "end": iso(right), "state": color, "seconds": {k: round(v, 3) for k, v in seconds.items()}})
    known = totals["UP"] + totals["DOWN"]
    monitored = known + totals["UNKNOWN"]
    events = [{"started_at": iso(a), "ended_at": iso(b) if b < end else None,
               "duration_seconds": round((b-a).total_seconds(), 3), "reason": reason,
               "continues_from_before_window": a == start} for a, b, state, reason in segments if state == "DOWN"]
    return {"target_id": target_id, "period": period, "start": iso(start), "end": iso(end),
            "recorded_since": iso(cursor.recorded_since) if cursor else None,
            "seconds": {k: round(v, 3) for k, v in totals.items()},
            "uptime_percent": round(totals["UP"] / known * 100, 4) if known else None,
            "coverage_percent": round(known / monitored * 100, 4) if monitored else None,
            "window_coverage_percent": round(known / (end-start).total_seconds() * 100, 4),
            "downtime_count": len(events), "longest_down_seconds": max((event["duration_seconds"] for event in events), default=0),
            "buckets": buckets, "downtimes": list(reversed(events[-100:])), "downtimes_truncated": len(events) > 100}


def prune(session, retention_days=365, batch_size=1000):
    cutoff = now() - timedelta(days=retention_days)
    old = list(session.scalars(select(AvailabilityInterval).where(AvailabilityInterval.ended_at < cutoff).order_by(AvailabilityInterval.id).limit(batch_size).with_for_update()))
    columns = {"UP": "up_seconds", "DOWN": "down_seconds", "UNKNOWN": "unknown_seconds", "DISABLED": "disabled_seconds"}
    for interval in old:
        left = interval.started_at
        while left < interval.ended_at:
            midnight = datetime.combine(left.date() + timedelta(days=1), time.min)
            right = min(midnight, interval.ended_at)
            daily = session.get(AvailabilityDaily, (interval.target_id, left.date()))
            if daily is None:
                daily = AvailabilityDaily(target_id=interval.target_id, day=left.date(), up_seconds=0, down_seconds=0, unknown_seconds=0, disabled_seconds=0, downtime_count=0)
                session.add(daily)
            column = columns[interval.state]
            setattr(daily, column, getattr(daily, column) + (right-left).total_seconds())
            if interval.state == "DOWN" and left == interval.started_at:
                daily.downtime_count += 1
            left = right
        session.delete(interval)
    return len(old)
