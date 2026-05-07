# 品牌主题替换说明

用于给不同客户或不同版本快速替换启动器品牌，不需要改前端代码。

## 需要替换的位置

默认品牌主题位于：

```text
openclaw_new_launcher/data/themes/default/
  theme.json
  logo.png
```

打包后对应：

```text
OpenClawFiles/data/themes/default/
  theme.json
  logo.png
```

## 可改内容

`theme.json` 里常用字段：

```json
{
  "brand": {
    "name": "永浩科技",
    "subtitle": "智能AI服务平台",
    "terminal_header": "Service Console",
    "logoUrl": "logo.png"
  },
  "window": {
    "title": "永浩科技 - 智能AI服务平台"
  },
  "modes": {
    "light": {
      "accent": "#1A56DB",
      "accent_hover": "#1444AD",
      "accent_soft": "#E4E8F0",
      "accent_ink": "#0F327F"
    },
    "dark": {
      "accent": "#9D4EDD",
      "accent_hover": "#B76BFF",
      "accent_soft": "rgba(157, 78, 221, 0.18)",
      "accent_ink": "#F5EAFF"
    }
  }
}
```

`logoUrl` 可以写同目录图片名，例如 `logo.png`。替换 Logo 时保持文件名不变最稳。

## 打包建议

1. 先替换 `data/themes/default/theme.json` 和 `data/themes/default/logo.png`。
2. 再运行打包脚本。
3. 打包完成后检查根目录仍然只有 `OpenClaw.exe` 和 `OpenClawFiles`。

## 注意

当前方案是“方便出定制包”，不是防客户篡改。后续商业版可以加主题签名或授权服务器下发主题。
