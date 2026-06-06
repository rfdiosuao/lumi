# Luminode Desktop Agent 闆嗘垚鏂规

## 瀹氫綅

Luminode 涓嶅悎骞惰繘鍚姩鍣ㄦ湰浣擄紝鑰屾槸浣滀负鍙€?sidecar锛?
- 鍚姩鍣ㄨ礋璐ｅ彂鐜般€侀厤缃€佸惎鍔ㄣ€佸仠姝€佸仴搴锋鏌ュ拰鏃ュ織锛?- Luminode 璐熻矗妗岄潰鎴浘銆佺偣鍑汇€佽緭鍏ュ拰寰俊鐩稿叧 RPA锛?- OpenClaw 閫氳繃鍚姩鍣?Bridge 璋冪敤 `/api/desktop-agent/*`锛屼笉鐩存帴璇诲彇 token銆?
## 閰嶇疆

绉佹湁閰嶇疆鏂囦欢锛?
```text
data/.openclaw/launcher/desktop-agent.json
```

涓昏瀛楁锛?
- `agentDir`: Luminode 鐩綍锛岀暀绌烘椂鑷姩鏌ユ壘鐩搁偦 `agents/luminode-desktop`
- `port`: 榛樿 `21900`
- `token`: 鍚姩鍣ㄨ嚜鍔ㄧ敓鎴愶紝涓嶅睍绀烘槑鏂?- `appType`: `weixin` 鎴?`wework`
- `autoStartHttpApi`: 鍚姩 Luminode 鏃惰嚜鍔ㄦ媺璧锋湰鍦?HTTP API

## Bridge API

- `GET/POST /api/desktop-agent/status`
- `POST /api/desktop-agent/config`
- `POST /api/desktop-agent/start`
- `POST /api/desktop-agent/stop`
- `GET/POST /api/desktop-agent/health`
- `POST /api/desktop-agent/screenshot`
- `POST /api/desktop-agent/click`
- `POST /api/desktop-agent/type`
- `POST /api/desktop-agent/wechat/send`
- `POST /api/desktop-agent/wechat/unread`

## 瀹夊叏

- Luminode 鍙洃鍚?`127.0.0.1`
- 鏈湴 HTTP API 鏀寔 `X-Desktop-Agent-Token` 鍜?`Authorization: Bearer`
- OpenClaw 涓嶅簲璇ユ嬁 token锛屽繀椤昏蛋鍚姩鍣?Bridge
- 鑷姩鍥炲鍜岀湡瀹炶仈绯讳汉娑堟伅鍙戦€佸繀椤绘湁鐢ㄦ埛鏄庣‘鎰忓浘

## 鍚庣画鍊?
- 琛ラ綈 WebSocket OpenClaw Node 鍗忚
- 缁?Luminode 鎵撶嫭绔嬩究鎼哄寘骞舵斁鍏?`OpenClawFiles/agents/luminode-desktop`
- 妗岄潰 Agent 鍔犵幆澧冭瘖鏂細绔彛鍗犵敤銆丒lectron 缂哄け銆乺obotjs 鍘熺敓妯″潡鎹熷潖銆佸井淇＄獥鍙ｄ笉鍙
- 缁?OpenClaw 澧炲姞妗岄潰鎵ц CLI helper
