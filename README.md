# 快阅 (KuaiYue)

ComfyUI 图片浏览筛选工具。本地 Web 服务，快速审阅、筛选、下载 AI 生成图片。

## 功能

- 暗色网格画廊，按时间倒序浏览
- 前缀分组过滤（如 `firefly_`、`nahida_`）
- 移动端适配：单击预览、长按选中模式切换、滑动浏览
- 用户登录，角色权限（管理员 / 普通用户）
- 管理员：查看、删除（回收站可恢复）
- 所有用户：查看、单张下载、多张打包 ZIP 下载
- 预览模式左右滑动/点击切换

## 快速开始

```bash
pip install flask werkzeug

# 启动
python3 app.py --dir /path/to/images --port 8899

# 访问
# http://localhost:8899
```

## 默认账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin  | admin123 | 管理员（全部权限） |
| user   | user123  | 普通用户（查看+下载） |

> ⚠️ 首次使用请修改默认密码，或通过管理员 API 创建新用户后删除默认账号。

## API

```bash
# 登录
POST /api/login  {"username":"admin","password":"admin123"}

# 查看图片列表
GET /api/images?prefix=firefly_

# 单张下载
GET /api/download/<filename>

# 批量下载 (ZIP)
POST /api/download-batch  {"files":["a.png","b.png"]}

# 删除 (管理员)
POST /api/delete  {"files":["a.png"]}

# 用户管理 (管理员)
GET  /api/users
POST /api/users  {"username":"new","password":"pw","role":"user"}
DELETE /api/users/<username>
```

## 部署

```bash
# systemd 服务
sudo cp image-review.service /etc/systemd/system/
sudo systemctl enable --now image-review.service
```
