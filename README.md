# B站热词榜

一个本地小工具，用来定时采集 B 站热搜关键词，保存快照，并按天生成 CSV 和 HTML 报告。

## 它能做什么

- 抓取 B 站热搜关键词、排名、热度值 `heat_score`
- 保存到本地 SQLite 数据库
- 汇总每日关键词：
  - 最高热度
  - 平均热度
  - 上榜次数
  - 最高排名
  - 首次/最后出现时间
  - 热度趋势
- 生成 `reports/bili_hotwords_YYYY-MM-DD.html`
- 生成 `reports/bili_hotwords_YYYY-MM-DD.csv`
- 提供本地可视化看板，支持日期切换、Top N、趋势图、热度排行和手动采集
- 支持热词反查，输入关键词后查看最近榜单里的相关词条

## 一键运行

在 PowerShell 中进入本目录，然后运行：

```powershell
.\run_once.cmd
```

这会执行一次采集，并生成当天报告。

如果你更想直接运行 PowerShell 脚本，可以使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_once.ps1
```

如果你安装了系统 Python，也可以直接运行：

```powershell
python .\bili_hotwords.py collect
python .\bili_hotwords.py report
```

当前 Codex 桌面环境里也自带 Python，`run_once.ps1` 会优先使用它。

## 可视化看板

启动本地看板：

```powershell
.\run_dashboard.cmd
```

默认地址：

```text
http://127.0.0.1:8765/
```

看板可以读取本地数据库，并从界面触发一次新的采集。

看板里的“热词反查”可以输入关键词，例如 `高考`，查询最近榜单中包含该词的相关热词，最多展示 100 条。

## 常用命令

采集一次：

```powershell
python .\bili_hotwords.py collect
```

生成今天的日报：

```powershell
python .\bili_hotwords.py report
```

生成指定日期日报：

```powershell
python .\bili_hotwords.py report --date 2026-06-25
```

前台循环采集，每 10 分钟一次，并在每次采集后刷新报告：

```powershell
python .\bili_hotwords.py loop --interval-minutes 10 --report
```

## 定时任务

可以用 Windows 任务计划程序定时执行 `run_once.ps1`。

也可以用脚本注册一个每 10 分钟运行一次的任务：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_windows_task.ps1 -IntervalMinutes 10
```

任务名是 `BiliHotwordsCollector`。如果你想停止它，可以在“任务计划程序”里禁用或删除这个任务。

## 文件说明

- `bili_hotwords.py`：主程序，包含采集、入库、日报生成、循环采集
- `dashboard.py`：本地可视化看板
- `run_once.ps1`：一键采集一次并生成报告
- `run_dashboard.ps1`：启动本地看板
- `install_windows_task.ps1`：注册 Windows 定时任务
- `data/bili_hotwords.sqlite3`：本地数据库，首次采集后自动生成
- `reports/`：日报输出目录

## 数据来源和注意事项

工具使用 B 站公开网页接口生成本地快照。网页接口可能变化，也不等于官方长期承诺的开放 API。建议保持低频采集，例如 5 到 15 分钟一次，不要高并发请求。

日报不是 B 站官方“每日榜”，而是基于你本地采集快照汇总出来的每日热词榜。采集越稳定，日报越有参考价值。
