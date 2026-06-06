# 快速上手

主线雷达有两种用法：**离线演示**（合成数据，立刻可玩）与**真实使用**（采集 A 股真实数据）。

## 安装

```bash
pip install -r requirements.txt
pip install -e .          # 安装后可用 `alpharadar` 命令
```

## 路线 A：离线演示（无需联网，5 秒上手）

```bash
alpharadar demo                          # 灌入合成演示数据
alpharadar ui                            # 打开图形界面（推荐）
# 或纯命令行：
alpharadar run ai_optical_module --as-of 2021-12-31
alpharadar mine                          # 训练市场状态规律
alpharadar backtest                      # 历史回测
```

> 演示数据是**人造**的，仅用于体验流程与界面，不含真实市场信息。

## 路线 B：真实使用（需在可访问东方财富的机器上）

> ⚠️ 云端/受限网络会拦截数据源（返回 403），请在本地或可联网环境运行。

```bash
# 1) 采集某条主线的候选股 + 指数 + 财务
alpharadar sync ai_optical_module

# 2) 出一份研究报告（市场状态→激活→选股→报告）
alpharadar run ai_optical_module --save

# 3) （可选）训练规律并回测：先采一大批股票池
alpharadar sync-universe --board BK0457 --with-financials   # 光通信板块
#   或全市场（慢）：alpharadar sync-universe --limit 300 --with-financials
alpharadar mine                          # 按市场状态训练因子权重
alpharadar backtest --save               # 历史回放验证
alpharadar run ai_optical_module         # run 会自动叠加学到的「规律信号」
```

## 命令速查

| 命令 | 作用 |
|------|------|
| `demo` | 灌入合成演示数据 |
| `ui` | 启动图形界面（Streamlit） |
| `sync <theme>` | 采集主线候选股 + 指数 + 财务 |
| `sync-universe` | 采集一大批股票（供挖掘/回测）|
| `regime` | 判断当前市场状态 |
| `theme <theme>` | 主线收敛链（激活/瓶颈/候选池）|
| `score <theme>` | 候选池基本面打分 |
| `mine` | 训练不同市场状态下的上涨规律 |
| `backtest` | 历史回放统计超额/IR/胜率/回撤 |
| `run <theme>` | 端到端：市场状态→激活→选股→报告 |

## 数据放在哪

默认落地到 `./data_store`（parquet 行情 + SQLite 水位线 + `patterns.json` 规律库），
已在 `.gitignore` 中忽略，不入库。删除该目录即清空所有本地数据。

## ⚠️ 重要提醒

- 本工具是**研究/教育**用途，所有输出为基于历史数据的统计分析，**不构成投资建议**。
- 规律挖掘与回测目前为**样本内**评估，真实有效性需在真实 15 年数据上、用滚动重训验证。
- 流动性维度待宏观数据接入；估值/景气因子待补（见 `docs/roadmap.md`）。
