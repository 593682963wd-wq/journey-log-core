# 私人旅程记录组件

保留原SQLite记录仓库、增改/软删除、重复检测、批次/附件元数据、审计及统计；来源只接受用户显式记录。

## 使用

Python 3.11+。在本目录建立独立虚拟环境：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python cli.py example.json
.venv/bin/python -m unittest discover -v
```

`example.json`从零编写，仅含虚构输入。可以显式提供自己的同结构JSON文件。输出默认为终端；`--output result.json`使用独占创建，避免覆盖已有结果。CLI失败退出码2。

## 数据与边界

不发现本机账号、不读取环境中的模型密钥、不发送消息、不请求远端数据。只处理调用方明确传入的文件、记录或参数。合成示例不代表任何实际业务结果。没有公司数据接口、机场来源合同、真实行程/同行人、附件或地图服务。原模型内部ICAO字段现仅用于通用起终点文字；UI展示调用方提供的名称。

## 发布状态

本项目源码采用 MIT 许可证，见 LICENSE。依赖按各自上游许可使用，安装的依赖/模型/字体/媒体不随此源码目录分发。

## 2026-11-08 协作修订

- 更新保留备注、标签等元数据。
- 时长和距离在写入前校验。
- 业务去重不含id；路线身份使用JSON端点数组，避免连字符碰撞。

集合根目录 `verify_release.py --project personal-journey-log` 可复跑合成测试和首次使用示例；本轮以集合验证报告为准。
