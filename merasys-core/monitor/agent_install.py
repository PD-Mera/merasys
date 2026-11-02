"""Public, source-only agent download; credentials are supplied on the target server."""
import io
import tarfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

SOURCE = Path('/app/agent-source')
if not SOURCE.is_dir():
    SOURCE = Path(__file__).resolve().parents[2] / 'merasys-agent'
FILES = ('install.sh', 'monitor-agent.py', 'merasys-agent.service')


def attach(app):
    @app.get('/agent/install.sh')
    def install_script():
        path = SOURCE / 'install-from-core.sh'
        if not path.is_file():
            raise HTTPException(503, 'Chưa mount source agent')
        return FileResponse(path, media_type='text/plain', headers={'Cache-Control': 'no-store'})

    @app.get('/agent/bundle.tar.gz')
    def bundle():
        if any(not (SOURCE / name).is_file() for name in FILES):
            raise HTTPException(503, 'Chưa mount đầy đủ source agent')
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:gz') as archive:
            for name in FILES:
                archive.add(SOURCE / name, arcname=name, recursive=False)
        return Response(output.getvalue(), media_type='application/gzip', headers={'Cache-Control': 'no-store'})
