# 数据模型与数据源

> 对应第 1 层 `data`。本文定义系统需要哪些「关联数据」、来自哪里、以什么结构存储。

## 1. 四类关联数据

系统的核心是把以下四类数据**关联**起来分析（这正是「分析关联数据」的含义）：

| 类别 | 内容 | 频率 | 主要用途 |
|------|------|------|----------|
| **行情 Market** | 个股/指数/行业的开高低收、成交量额、换手、复权因子 | 日 | 动量、市场状态、回测收益 |
| **财务 Financials** | 三大报表、关键比率（营收增速、毛利率、ROE、现金流） | 季 | 公司基本面打分 |
| **宏观 Macro** | GDP、CPI、PPI、PMI、M2、社融、利率、汇率 | 月/季 | 市场状态、政策环境 |
| **行业 Industry** | 行业指数、景气指标、产业链上下游量价（如光模块出货、800G 渗透率） | 月/季 | 行业景气、主线判断 |
| **政策/事件 Policy** | 政策文件、产业规划、重大事件（结构化标签 + 原文链接） | 事件驱动 | 主题触发、定性增强 |

> 政策类数据先以**人工维护的事件表 + 标签**形式接入（见 `config/themes/*.yaml` 的 `policy_signals`），
> 后续可引入 NLP 自动抽取。

## 2. 数据源

### 主数据源：EastmoneySource（内置，直连东方财富）
- **零额外重依赖**，仅用 `requests`，直连东方财富公开行情/财务接口（akshare 底层也是调它）。
- 已实现：日线行情（后复权）、指数行情、业绩报表（含**公告日 ann_date**）、行业板块成分。
- 设计上**解析逻辑与 HTTP 抓取分离**：`parse_kline` / `parse_financials` 等纯函数可用
  离线样本完全单测（见 `tests/test_data.py` 与 `tests/fixtures/`），抓取层只是薄壳。
- 限速 / 重试在 `data/http.py::HttpClient` 统一处理（4xx 不无谓重试）。
- 待接入：宏观指标 `macro()`。

### 可选补充
- **AKShare**：社区封装，覆盖更全（含宏观）；作为可选适配器（`AkshareSource`）。
- **Tushare Pro**：质量高、字段全，但需积分 token。适合财务与 point-in-time 数据。
- **baostock**：免费历史行情，作为行情交叉校验。

> ⚠️ 这些数据源主机（eastmoney/sina 等）在受限网络（如本项目的云执行环境白名单代理）
> 下可能被拦截（返回 403）。需在能访问数据源的机器上运行采集（`alpharadar sync`）。

所有数据源都实现统一接口 `data/sources/base.py::DataSource`，上层只依赖接口，不依赖具体源。

## 3. 统一接口（核心抽象）

```python
class DataSource(ABC):
    def daily_bars(symbols, start, end) -> DataFrame    # 行情
    def financials(symbols, start, end) -> DataFrame    # 财务
    def macro(indicators, start, end) -> DataFrame      # 宏观
    def industry_members(industry) -> DataFrame         # 行业成分
    def index_bars(index_code, start, end) -> DataFrame # 指数行情
```

返回的 DataFrame 遵循下文的标准列定义，**与数据源无关**。

## 4. 标准数据结构（Schema）

> 列名统一用英文小写下划线，日期统一 `datetime64[ns]`，股票代码统一 6 位 + 交易所后缀（如 `300308.SZ`）。

### 4.1 行情 `daily_bars`
| 列 | 类型 | 说明 |
|----|------|------|
| `symbol` | str | `300308.SZ` |
| `date` | date | 交易日 |
| `open/high/low/close` | float | 后复权价 |
| `volume` | float | 成交量（股） |
| `amount` | float | 成交额（元） |
| `turnover` | float | 换手率 |
| `adj_factor` | float | 复权因子 |

### 4.2 财务 `financials`（point-in-time）
| 列 | 类型 | 说明 |
|----|------|------|
| `symbol` | str | 股票代码 |
| `report_period` | date | 报告期（如 2026-03-31） |
| `ann_date` | date | **公告日**（决定何时可用，防未来函数） |
| `revenue` | float | 营业收入 |
| `revenue_yoy` | float | 营收同比 |
| `net_profit` | float | 归母净利润 |
| `net_profit_yoy` | float | 净利同比 |
| `gross_margin` | float | 毛利率 |
| `roe` | float | 净资产收益率 |
| `ocf` | float | 经营性现金流 |
| `capex` | float | 资本开支（看产能扩张） |

> `ann_date` 是关键：回测时「某日可用的财务」= `ann_date <= 当日` 的最新一期。

### 4.3 宏观 `macro`
| 列 | 类型 | 说明 |
|----|------|------|
| `indicator` | str | `cpi_yoy` / `pmi` / `m2_yoy` / `shibor_3m` ... |
| `date` | date | 数据所属期 |
| `ann_date` | date | 公布日 |
| `value` | float | 数值 |

### 4.4 行业 `industry`
| 列 | 类型 | 说明 |
|----|------|------|
| `industry_code` | str | 行业/概念代码 |
| `date` | date | |
| `index_close` | float | 行业指数 |
| `prosperity` | float | 景气度（量价/出货等合成，见 methodology） |
| `member_symbols` | list[str] | 成分股 |

## 5. 存储布局

```
data_store/                 # 见 .gitignore，不入库
├── meta.sqlite             # 元数据：股票列表、行业映射、采集水位线
├── bars/                   # 行情，按年分区 parquet
│   └── year=2026/part.parquet
├── financials/             # 财务 parquet
├── macro/                  # 宏观 parquet
└── industry/               # 行业 parquet
```

- **时间序列** → parquet 列存，DuckDB 直接 SQL 查询，免数据库部署。
- **元数据/水位线** → SQLite，记录每个表「采到哪天了」，支持增量更新。
- **point-in-time** → 财务与宏观都存 `ann_date`，回测按公告日切片。

## 6. 采集策略（`data/ingest.py`）

1. **增量更新**：读 SQLite 水位线，只补缺失区间。
2. **限速 + 重试**：指数退避，避免被数据源封禁。
3. **校验**：行情做基本一致性检查（价格非负、复权连续）。
4. **可重放**：原始响应可选缓存，便于复现与排错。

## 7. 数据质量与陷阱

- ⚠️ **复权**：因子计算一律用后复权价，避免除权跳空污染动量。
- ⚠️ **幸存者偏差**：股票池需包含退市股，回测才不失真（15 年里有大量退市/ST）。
- ⚠️ **未来函数**：财务一律按 `ann_date` 而非 `report_period` 切片。
- ⚠️ **停牌/涨跌停**：回测成交假设需考虑无法成交的情形。
