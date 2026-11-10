# AI 竞赛导航 (ai-arena)

**线上地址：<http://ai.moonstack.org>**（HTTPS 证书由 GitHub 自动签发中，就绪后直接可用 https 访问；`Settings → Pages → Enforce HTTPS` 可勾选强制加密跳转）

自动采集 + 自动更新的 AI 竞赛导航站。每天定时抓取在途奖金赛,渲染成单页 HTML,托管到 GitHub Pages 后全网可访问。

## 当前自动采集源

| 源 | 方式 | 代理 |
|---|---|---|
| Zindi | 官方 API (`api.zindi.africa/v1/competitions`) | 境外,本地跑需梯子 |
| DrivenData | 列表页结构化 data-* 属性解析 | 境外,本地跑需梯子 |
| DataFountain | 列表页 HTML 解析 | 国内直连 |

人工维护源(公众号类赛事、永续平台、避坑清单、2027 日历)在 `curated.json`,无结构化接口,由 AI/人工定期更新。

## 文件结构

```
ai-arena/
├── main.py                     # 采集+渲染一体机(纯 Python 标准库,零依赖)
├── curated.json                # 人工情报库
├── index.html                  # 生成产物(发布物)
├── data.json                   # 采集原始快照
├── README.md
└── .github/workflows/update.yml # 云端每日自动采集+发布
```

## 本地运行(Windows)

```powershell
cd G:\talk\ai-arena
$env:ARENA_PROXY='http://127.0.0.1:7897'   # 梯子地址,没有就删掉这行
python main.py
```

跑完双击 `index.html` 即可查看。不设代理时境外源会失败(国内源不受影响),页面会如实标注哪些源异常。

## 发布到 GitHub Pages(一次性,三步)

```powershell
cd G:\talk\ai-arena
gh auth login                          # 1. 登录(浏览器授权,一次性)
gh repo create ai-arena --public --source=. --push   # 2. 建仓库并推送
gh api -X POST repos/{owner}/ai-arena/pages -f "source[branch]=main" -f "source[path]=/"   # 3. 开启 Pages
```

之后访问 `https://<你的用户名>.github.io/ai-arena/` 即为线上地址。
**每天 UTC 00:30(北京时间 08:30)GitHub 云端自动采集重发**,无需本地电脑开机。
也可在仓库 Actions 页 → Daily Update → Run workflow 手动触发。

## 维护

- **自动源**: 无需维护。Zindi/DrivenData/DF 出新赛自动出现在"进行中"区。
- **人工源**: 让 AI 更新 `curated.json`(windows 字段=在途窗口, 过期自动隐藏; watch=避坑清单; calendar=未来日历), 提交 push 后下次自动生效。
- **注意事项**:
  - GitHub 定时任务在仓库连续 60 天无活动后会暂停,偶尔手动触发一次即可;
  - 当前 git 凭据的 token 无 `workflow` scope:改 `.github/workflows/update.yml` 时 push 会被拒,需走网页编辑或换带 workflow scope 的授权;普通文件(index.html/curated.json 等)push 不受影响;
  - 不要把已备案的域名(如 jinshisec.com)绑到 GitHub Pages——备案域名指向境外服务器可能被管局注销备案,moonstack.org 无备案包袱,随便绑子域;
  - 国内直连访问 GitHub Pages 偶尔不稳,访问不了就挂梯子。

## 阅读口径

- "已报名"人数为注册数,实际认真参赛队伍远少于此(Zindi 尤甚);
- 奖金/截止时间以各赛官网为最终准,本站是雷达不是合同;
- DrivenData 部分赛为美国联邦资助(如 American-Made 系列),报名前自查参赛资格;
- Zindi 个别比赛限国别,报名前读 Rules 页 Eligibility 段。
