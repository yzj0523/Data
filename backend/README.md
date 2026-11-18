# Python 后端

后端提供问答、会话、数据源、配置和反馈等 API。演示数据字典与独立核对 SQL 见 [指标字典](../docs/指标字典.md)。

## 环境与安装

支持 Python 3.11–3.13，依赖及版本范围见 `pyproject.toml`。以下命令均在 `backend/` 中执行。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m app
```

Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m app
```

仅安装运行依赖时使用 `python -m pip install -e .`。这里的 `python` 指虚拟环境解释器；也可先激活虚拟环境，再执行后文的 `python` 命令。

默认监听 `http://127.0.0.1:8000`。所有API以 `/api` 为前缀，接口说明位于 `/api/docs`。

开始问数前，在激活虚拟环境的 `backend/` 中运行 `python -m app.seed`。需要真实问答时，通过 `AI_DEFAULT_MODEL_BASE_URL`、`AI_DEFAULT_MODEL_NAME` 和 `AI_DEFAULT_MODEL_API_KEY` 配置支持 JSON 对象输出的 OpenAI 兼容模型。

## 环境配置

可复制 `.env.example` 为 `backend/.env`，也可直接设置环境变量。环境变量优先于 `.env`。在 `backend/` 启动时读取该目录下的 `.env`；运行期间修改配置需要重新启动服务。

| 配置项 | 默认值 | 含义 |
|---|---|---|
| `AI_ENVIRONMENT` | `development` | `development`、`test` 或 `production` |
| `AI_HOST` | `127.0.0.1` | 监听IPv4或IPv6地址，例如 `0.0.0.0` |
| `AI_PORT` | `8000` | 1–65535的监听端口 |
| `AI_LOG_LEVEL` | `info` | `critical`、`error`、`warning`、`info`、`debug` |
| `AI_DATABASE_PATH` | `data/ai_query.sqlite3` | 数据库文件路径；相对路径相对于启动目录，不能是空白或现有目录 |
| `AI_DEFAULT_MODEL_BASE_URL` | 未配置 | 可选的HTTP/HTTPS模型地址 |
| `AI_DEFAULT_MODEL_NAME` | 未配置 | 可选的模型名称 |
| `AI_DEFAULT_MODEL_API_KEY` | 未配置 | 可选的模型密钥；不提交到版本控制 |
| `AI_MODEL_ENCRYPTION_KEY` | 本地生成 | 自定义模型凭证的 Fernet 主密钥。未配置时在库文件旁保存 `.model-key`，备份和恢复需保留该文件 |
| `AI_QUESTION_MAX_LENGTH` | 2000 | 当前环境允许的问题字符数 |
| `AI_QUERY_MAX_ROWS` | 200 | 当前环境允许的查询结果上限 |
| `AI_QUERY_TIMEOUT_SECONDS` | 2 | SQLite 查询超时秒数 |
| `AI_MODEL_TIMEOUT_SECONDS` | 15 | 问答模型 HTTP 超时秒数 |

模型字段留空或纯空白时视为未配置。没有模型凭证也可以启动。健康检查只读取配置。模型测试与问答请求会实际调用外部服务，接受公开 HTTPS 地址。

配置验证失败时，`python -m app` 返回非零退出码，只输出出错字段名，不输出原始值或堆栈。`debug` 日志级别不会启用HTTP调试堆栈。

## 健康检查与错误格式

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

```bash
curl http://127.0.0.1:8000/api/health
```

有效配置且未设置完整模型凭证时，返回HTTP 200：

```json
{"status":"ok","environment":"development","model":{"status":"not_configured"}}
```

模型地址、名称、密钥均已配置时，模型状态为 `not_checked`，仅表示连接尚未验证。健康检查只证明当前HTTP服务可用，不证明数据库或模型可用，也不会回显路径、地址或密钥。

如需以固定监听参数诊断环境配置，可使用：

```bash
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

此方式的监听参数由Uvicorn命令行决定。若应用环境配置无效，`GET /api/health` 返回HTTP 503，例如：

```json
{"error":{"code":"configuration_error","message":"Invalid server configuration.","fields":["AI_PORT"]}}
```

HTTP错误统一使用 `{"error":{"code":"...","message":"..."}}`，配置错误可额外返回安全的 `fields`。当前包括404 `not_found`、405 `method_not_allowed`、422 `validation_error`、500 `internal_error`。响应不包含请求原值或异常堆栈。

未处理的HTTP异常由中间件拦截，日志只记录固定错误事件，不记录原始异常、异常链或密钥。响应尚未开始时返回统一500；响应传输中失败时保留连接中断行为，仅向服务器传递固定错误信息；响应已完成后的后台任务失败只记录安全事件。

## 测试

在已安装测试依赖的虚拟环境中运行：

```bash
python -m pytest -q
```

测试通过HTTP验证健康状态、无/部分/完整模型配置、配置异常、`.env`与环境变量优先级、未知路径和统一错误格式，并通过命令行验证配置错误退出。子进程在受控临时目录启动，不读取工作副本的 `.env`。回归测试还会在带有无效 `.env` 的受控工作副本中运行CLI测试，验证其隔离性。

真实Uvicorn子进程测试通过本机回环HTTP检查普通异常、异常链、流式中断及后台任务失败，并读取进程日志验证无模拟密钥泄露；子进程结束后自动停止。500及422测试端点只在测试中注册，正式服务不会提供这些路径。测试需要允许监听本机回环端口。

业务测试使用各自的临时 SQLite 数据库以及供应商 HTTP 替身，全部使用模拟凭证。若系统旧的 pytest 临时目录无法访问，可指定新的测试目录，例如 `python -m pytest -q -p no:cacheprovider --basetemp .venv/pytest-run`。容器运行和重启验证见 [部署说明](../docs/部署.md)。
