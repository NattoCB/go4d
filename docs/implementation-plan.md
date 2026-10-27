# 四维围棋 Implementation Plan

> **For agentic workers:** Use subagent-driven-development for independent engine and view work; the primary agent reviews and integrates.

**Goal:** 交付一个免依赖安装、可操作且规则可核验的 Python 四维围棋小游戏。

**Architecture:** engine.py 保存棋局；ai.py 选择合法落子；app.py 提供本地 HTTP；static/ 提供切片可视化。

**Tech Stack:** Python 3.10+ 标准库，原生 HTML/CSS/JavaScript/SVG。

**Spec:** docs/design.md

## Global Constraints

- 四轴正交邻接，坐标 (x,y,z,w)，每轴 3–5 点，无环绕。
- Python 是唯一规则来源，无第三方安装；仅绑定 127.0.0.1。
- 白贴 0.5 默认可调；面积法及死子由双方确认；启发式电脑执白。

## Task 1: 规则与电脑

- [x] 先写 unittest 行为测试，运行并记录红灯，再实现 engine.py / ai.py。
- [x] Game 暴露 play(point)、pass_turn()、undo()、resign()、toggle_dead(point)、resume()、to_dict()、export_data()、from_data(data)；BLACK=1，WHITE=2；board 按 x 最快存储。
- [x] choose_move(game, seed=None) 返回合法坐标或 None；hint 不改棋局。
- [x] 验证跨切片气与提子、重现禁着、无副作用失败、终局计分与损坏存档拒绝。

## Task 2: 可视化

- [x] static/index.html、style.css、app.js 提供 SVG 切片矩阵，颜色与坐标图例，悬停邻点/整块气、轴交换、操作与存档。
- [x] GET /api/state 获取 {revision,mode,game}；POST /api/action 提交 {action,revision,…} 返回同格式；export/import 为 JSON 下载/上传。
- [x] UI 交互由真实浏览器验证，包括窄屏、焦点与键盘落子。

## Task 3: 本地服务与集成

- [x] 先写 HTTP 行为测试（预期服务缺失），再实现 app.py。
- [x] run python3 -m unittest discover -s tests -v；HTTP 断言棋局修改、非法输入不变、冲突返回 409、Origin 拒绝。
- [x] 运行 python3 app.py --no-browser --port 0，打开返回地址；浏览器走落子→提子→悔棋→保存→恢复→终局，截取界面。
- [x] 写 README、启动脚本、标准库打包脚本；fresh 验证后仅提交项目文件、合入 dev 并生成 zip。
