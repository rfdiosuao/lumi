# OpenClaw Launcher 商家 UI 主题管理

## 目录结构

```
themes/
├── _base/                      # 基准（原始 OpenClaw 状态，只读）
│   └── backup/                 # 原始文件备份（constants.py、logo 等）
├── _templates/                 # 商家主题模板
├── merchants/                  # 所有商家主题（每个商家一个目录）
│   └── <商家ID>/
│       ├── theme.json          # 主题元数据
│       ├── logo.ico            # 商家 Logo
│       ├── logo_square.ico     # 方形 Logo
│       ├── constants.py        # 该主题的颜色/字体/品牌配置
│       ├── preview.html        # 主题预览页
│       └── versions/           # 版本历史
│           ├── v1/
│           │   ├── constants.py
│           │   ├── theme.json
│           │   └── changelog.md
│           └── v2/
│               ├── constants.py
│               ├── theme.json
│               └── changelog.md
└── registry.json               # 总注册表（索引所有商家主题）
```

## 工作流程

### 新增商家主题
1. 提供商家品牌参数（名称、主色、风格、Logo）
2. 在 `merchants/<商家ID>/` 下生成主题文件
3. 初始版本记为 `v1`，存入 `versions/v1/`
4. 注册到 `registry.json`

### 切换主题
- 将目标商家的 `constants.py` 和 logo 复制到项目根目录即可生效

### 版本管理
- 每次修改主题时，新版本存入 `versions/vN/`
- `theme.json` 中记录版本历史和变更说明
- 可随时回滚到任意历史版本

## 命名规范
- 商家ID：小写英文 + 数字，如 `techcorp`、`ai_platform`、`smart_edu`
- 版本号：`v1`、`v2`、`v3`... 递增
