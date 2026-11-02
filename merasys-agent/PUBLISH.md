# Đưa toàn hệ thống lên cùng một repo Git

Agent là một folder trong repo chung với core và PostgreSQL, không init Git riêng trong folder agent. Làm theo [PUBLISH.md ở gốc repo](../PUBLISH.md). Git được khởi tạo trực tiếp tại thư mục ngoài cùng merasys:

```bash
git init -b main
git add .
git status --short
git diff --cached --stat
git commit -m "Prepare Merasys monitoring system"
git remote add origin https://github.com/PD-Mera/merasys.git
git push -u origin main
```

Nếu đã có .git/remote thì commit/push theo quy trình hiện tại, không chạy lại init/add remote. Dùng user.name/user.email Git của bạn nếu Git yêu cầu.

Chỉ .env.example/config.example.json có placeholder được commit. Không đưa .env, agent.env, config.json thật, git-update.json, private key hoặc token vào Git. Gitignore không gỡ secrets đã được track từ trước.

Sau khi push, trên mỗi server đã cài agent, upload git-update.sh và setup một lần:

```bash
sudo bash git-update.sh --setup https://github.com/PD-Mera/merasys.git main merasys-agent
sudo merasys-agent-update
```

Repo private cần quyền đọc Git cho root, xem GIT-UPDATE.md. Những lần sau: sửa code → commit/push → chạy `sudo merasys-agent-update` trên từng server. Lệnh không cập nhật core/env/token.

Sửa và commit trực tiếp trong repo gốc, không có bước xuất source. AGENT_SUBDIR khi setup là merasys-agent, không phải dấu chấm.
