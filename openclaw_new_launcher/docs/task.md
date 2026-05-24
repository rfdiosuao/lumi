# OpenClaw Launcher 褰撳墠浠诲姟娓呭崟

> 鏇存柊鏃ユ湡锛?026-05-24
> 褰撳墠鍒嗘敮閲嶇偣锛氭墜鏈虹纭害鏉熴€佺绾垮寘鍙戝寘绋冲畾鎬с€佹枃妗ｆ敹鍙ｃ€? 
> 妗岄潰瀹㈡湇 / SightFlow 鐩稿叧宸ヤ綔鏈湴淇濈暀锛屾殏涓嶇撼鍏ュ綋鍓?GitHub 鎺ㄩ€佹壒娆°€?

## 褰撳墠鐘舵€?

- 鍚姩鍣ㄧ増鏈熀绾匡細`2.0.6`
- APKClaw 楠屾敹鍩虹嚎锛歚6.26 / versionCode 860`
- 鎵嬫満 Agent 鍗忎綔鏂瑰紡锛歄penClaw 鍙兘閫氳繃 launcher CLI wrapper 鎸囨尌 APKClaw锛岄粯璁ゅ懡浠ゆ槸 `npm run phone:agent`
- 鎵嬫満绔?runtime context锛氫笉鏆撮湶鎵嬫満 IP銆佺鍙ｃ€乼oken 鍜屽簳灞?`/api/lumi/*` 浠诲姟绔偣
- 鍙戝寘鏍￠獙锛歚verify-release.ps1` 宸插己鍒舵鏌?phone wrapper銆亀orkspace銆乺untime context銆丄PK 闄勪欢鍜屾晱鎰熼厤缃?
- 鏂板绂荤嚎鍖?smoke锛歚scripts/verify-portable-smoke.ps1`
- 鐗堟湰涓€鑷存€э細`build-portable.ps1` 涓?`verify-release.ps1` 宸茶嚜鍔ㄦ鏌?package / Tauri / 鍖呭悕鐗堟湰涓€鑷达紝浠ュ強 `AgentPhone_latest.apk` 涓庣増鏈寲 APK 鐨?hash 涓€鑷存€?

## P0 浜や粯绋冲畾鎬?

### 1. 绂荤嚎鍖呭畬鏁存€ч獙鏀?

- [x] `verify-release.ps1` 妫€鏌?`openclaw-phone-agent.mjs`
- [x] `verify-release.ps1` 妫€鏌?OpenClaw workspace 鍥涗欢濂?
- [x] `verify-release.ps1` 妫€鏌?runtime context 涓嶉缃墜鏈鸿繛鎺?
- [x] `verify-release.ps1` 绂佹 runtime context 鏆撮湶搴曞眰鎵嬫満绔偣
- [x] `verify-portable-smoke.ps1` 妫€鏌?Python 渚濊禆 `fastapi/uvicorn`
- [x] `verify-portable-smoke.ps1` 妫€鏌?Node CLI 鑴氭湰璇硶
- [x] `build-portable.ps1` 鎺ュ叆 smoke 楠屾敹
- [x] 涓嬩竴娆℃寮?zip 鎵撳寘鍚庤窇瀹屾暣鐩綍 + zip 鍙岄獙鏀?

### 2. 浣庨厤涓€浣撴満鍚姩绋冲畾鎬?

- [x] 鍚姩瓒呮椂鏀惧锛屼綆閰嶆満鍣ㄥ惎鍔ㄦ參鏃朵繚鐣欒繘绋嬬户缁瓑寰?
- [x] 鍚姩澶辫触蹇収鍐欏叆 `data/logs/openclaw-startup-snapshot.json`
- [x] Bridge 鏈嶅姟鏃ュ織钀界洏鍒?`data/logs/bridge-service.log`
- [x] 缁х画鍑忓皯鍚姩棣栧睆闃诲妫€鏌?
- [x] 灏嗛潪鍏抽敭妫€鏌ユ噿鍔犺浇鍒扮幆澧冭瘖鏂〉
- [x] 鍚姩闃舵鑰楁椂鏃堕棿绾垮啓鍏ュ惎鍔ㄥ揩鐓у拰璇婃柇椤?
- [x] 鐜璇婃柇鏄剧ず鏈€杩戜竴娆″惎鍔ㄨ€楁椂銆佸綋鍓嶉樁娈靛拰蹇収璺緞
- [ ] 鍦?500 鍏冪骇涓€浣撴満涓婂仛鐪熷疄鍐峰惎鍔ㄨ鏃?

### 3. 鐜璇婃柇闂幆

- [x] 璇婃柇瀵煎嚭鍖呭惈鏃ュ織銆侀厤缃€佸惎鍔ㄥ揩鐓?
- [x] 璇婃柇鍙瘑鍒?Python/Node/WebView2 缂哄け
- [x] 璇婃柇鍙瘑鍒鍙ｅ崰鐢ㄥ拰娈嬬暀杩涚▼
- [x] 璇婃柇鍙瘑鍒?runtime-context 鍜屼究鎼哄寘鍏抽敭鏂囦欢缂哄け
- [x] 澧炲姞鏉€姣掕蒋浠舵嫤鎴彁绀?
- [x] 澧炲姞鈥滃叏缁夸絾鍚姩澶辫触鈥濈殑涓撻」鎽樿瑙勫垯

## P1 鎵嬫満 Agent / APKClaw

### 4. OpenClaw 鎸囨尌 APKClaw 纭害鏉?

- [x] 鏂板 `npm run phone:agent`
- [x] `openclaw-phone-agent` skill 鍐欏叆纭鍒欙細涓嶅緱鐩磋繛 APKClaw 浠诲姟绔偣
- [x] `AGENTS.md` 鍐欏叆纭鍒欙細涓嶅緱纭紪鐮併€佹帹鏂€佹墦鍗般€佽姹傛墜鏈?IP/绔彛/token
- [x] `runtime-context.json` 鏀逛负 `endpoint: launcher-cli-wrapper`
- [x] 鎵撳寘鑴氭湰鍐欏叆 wrapper-only runtime context
- [x] 缁?`phone:agent` 澧炲姞浠诲姟鍘嗗彶钀界洏
- [x] 缁?`phone:agent` 澧炲姞澶辫触鍒嗙被锛氱绾裤€佹湭鎺堟潈銆佹棤闅滅鍏抽棴銆佷换鍔¤秴鏃躲€丄PKClaw 宕╂簝銆佷换鍔″崰鐢?

### 5. APKClaw 绋冲畾鎬?

- [x] APKClaw 绔鍔犲穿婧冩棩蹇楀鍑?
- [x] APKClaw 绔?Agent worker 寮傚父鍏滃簳锛岄伩鍏?HTTP 鏈嶅姟涓€璧锋寕鎺?
- [x] 浠诲姟瓒呰繃 60 杞椂杩斿洖閮ㄥ垎缁撴灉鍜?follow-up 寤鸿
- [x] 閽堝璐墿/鎼滅储绫讳换鍔″浐鍖?`collect_list_items target=product`

### 6. 鎵嬫満婕旂ず鍦烘櫙

- [ ] 鍥哄寲涓€涓彲閲嶅 demo锛氭悳绱㈠晢鍝併€佹敹闆?10 涓€欓€夈€佽繑鍥炴€т环姣旀憳瑕?
- [ ] 鍥哄寲涓€涓彧璇?demo锛氳鍙栧綋鍓嶅睆骞曞苟杩斿洖鍙鍏ュ彛
- [ ] 鍥哄寲涓€涓瑙?fallback demo锛氫綆鑺傜偣/娓告垙鐢婚潰鏃惰蛋 `phone:game`

## P1 鍙戝竷涓?CI/CD

### 7. GitHub Release 鑷姩鍖?

- [x] GitHub 鍒嗘敮 `codex/phone-agent-hardguard` 宸叉帹閫?
- [x] 鎻愪氦 `1b2553f Add phone agent launcher wrappers`
- [x] 鎻愪氦 `26f52ab Add portable package smoke verification`
- [x] Release notes 榛樿涓枃
- [x] 正式 tag release 跑一完整 GitHub Actions（`v2.0.6` / run `26367646545`）
- [x] Release 闄勪欢纭鍖呭惈 portable zip銆乻ha256銆佸畨瑁呭櫒
- [x] Release 椤甸潰灞曠ず涓枃鏇存柊鎽樿鍜屾牎楠屽€?

### 8. 鐗堟湰鍙蜂竴鑷存€?

- [x] 鍚姩鍣ㄥ熀绾跨粺涓€鍒?`2.0.6`
- [x] `package.json` / `package-lock.json` 宸插悓姝?
- [x] 姣忔鍙戝寘鍓嶈嚜鍔ㄦ鏌?Tauri 鐗堟湰銆乸ackage 鐗堟湰銆佸寘鍚嶇増鏈竴鑷?
- [x] APKClaw latest 涓庣増鏈寲 APK 鏂囦欢 hash 涓€鑷存€ц嚜鍔ㄦ鏌?

## P1 鏂囨。鍊?

### 9. 鏂囨。鍏ュ彛鏀跺彛

- [x] 閲嶅啓 `DOCS_INDEX.md` 涓哄綋鍓嶆枃妗ｅ叆鍙?
- [x] 閲嶅啓 `task.md` 涓哄綋鍓嶅彲鎵ц浠诲姟娓呭崟
- [x] 娓呯悊鎴栨爣璁颁贡鐮佸巻鍙叉枃妗?
- [x] 鎶?`TECH_DEBT_LAUNCHER_AND_APKCLAW.md` 鏀规垚绮剧畝鍊哄姟鍙拌处
- [x] 鏇存柊 `RELEASE_CHECKLIST.md`锛屽姞鍏?`verify-portable-smoke.ps1`
- [x] 鏇存柊 `CUSTOMER_GUIDE.md`锛屽姞鍏?WebView2 鍜岀幆澧冭瘖鏂鏄?

### 10. 鏂囨。瑙勫垯

- [x] `DOCS_INDEX.md` 鏄庣‘浜嬪疄婧愪紭鍏堢骇
- [x] 鏂板鈥滄瘡娆℃敼鎺ュ彛蹇呴』鍚屾濂戠害 + 楠屾敹鑴氭湰鈥濈殑妫€鏌ラ」
- [x] 鏂板鈥滄瘡娆℃敼鍙戝寘娴佺▼蹇呴』鍚屾 release checklist鈥濈殑妫€鏌ラ」

## P2 妗岄潰 Agent / SightFlow

> 鏆傜紦鎺ㄩ€併€傚綋鍓嶆湰鍦板凡鏈夊疄楠屽疄鐜帮紝浣嗕笉杩涘叆鏈壒 GitHub 鍙樻洿銆?

- [ ] 鐢佃剳绔?Bridge-only 纭害鏉熸寮忔媶鍒嗘垚鍗曠嫭 PR
- [ ] SightFlow 閰嶇疆绛栫暐浜у搧鍖栵細鎴浘銆佺偣鍑汇€佽緭鍏ャ€佸井淇″彂閫佸紑鍏?
- [ ] 寰俊鍙戦€侀粯璁よ崏绋挎ā寮忥紝鐢ㄦ埛纭鍚庡啀鍙戦€?
- [ ] 妗岄潰 Agent 鐜璇婃柇锛歟xe 缂哄け銆佺鍙ｅ崰鐢ㄣ€乼oken 涓嶅尮閰嶃€佸井淇＄獥鍙ｄ笉鍙
- [ ] 鎵撳寘鏃舵槸鍚﹂檮甯?SightFlow sidecar 闇€鍗曠嫭璇勫

## 鎺ㄨ崘涓嬩竴姝?

1. 鎶婃湰娆℃枃妗ｅ€烘彁浜ゅ埌 GitHub锛屼笉鍖呭惈妗岄潰瀹㈡湇瀹炵幇銆?
2. 鏇存柊 `RELEASE_CHECKLIST.md`锛屾妸 smoke 楠屾敹鍔犲叆姝ｅ紡鍙戝寘娴佺▼銆?
3. 璺戜竴娆℃寮?zip 鎵撳寘锛岀‘璁ょ洰褰曞拰 zip 閮介€氳繃 `verify-release.ps1` 涓?`verify-portable-smoke.ps1`銆?
4. 鍐嶅鐞嗕綆閰嶄竴浣撴満鍚姩鎬ц兘锛氬噺灏戦灞忛樆濉炪€佸欢闀垮彲瑙嗗寲杩涘害銆佹噿鍔犺浇闈炲叧閿瘖鏂€?
## 褰撳墠杩樺€鸿繘搴?

- [x] 鎺堟潈鍚庡彴鏀规垚鍙鐨?SaaS 鎺у埗鍙版ā鏉?
- [x] 鏂板 `LICENSE_SERVER_SAAS_ADMIN_GUIDE.md`
- [x] 鏀寔鍗曚釜鎺堟潈鐮佺紪杈戞湀鍗″椁?
- [x] 鏀寔鎵归噺鎶婂巻鍙叉巿鏉冪爜鏀规垚鏈堝崱
- [x] 琛ユ巿鏉冨悗鍙版搷浣滃璁?
- [x] 琛ユ巿鏉冨悗鍙板彉鏇村墠鑷姩澶囦唤鍜屽洖婊氳鏄?
- [x] 琛ユ巿鏉冨悗鍙板椁愭ā鏉块厤缃拰濂楃敤
- [x] 琛ユ巿鏉冪爜鎼滅储銆佺瓫閫夈€佸垎椤?
- [x] 琛ユ縺娲昏鎯呭拰鍗曟潯璁惧瑙ｇ粦
- [x] 淇鎺堟潈鍚庡彴宸︿晶瀵艰埅鏃犲搷搴?
- [x] 淇鎺堟潈鍚庡彴绉诲姩绔《閮ㄦ寜閽孩鍑?
- [x] 缁х画鎶?`TECH_DEBT_LAUNCHER_AND_APKCLAW.md` 绮剧畝鎴愮湡姝ｇ殑鎵ц鍙拌处
## 褰撳墠鏀跺熬
- [x] 宸叉妸 `gatewayImageModel` 鍜?`gatewayVideoModel` 鎺ュ叆鍒扮綉鍏冲瓧娈?
- [x] 宸叉妸鐩稿叧鐣岄潰琛ラ綈鍒扮粺涓€鐨勬ā鍨嬮厤缃祦閲?
- [x] 宸叉妸浼氬憳缃戝叧閰嶇疆璇诲彇鏀跺彛鍒?`license / gatewayProfile / member`锛孫penClaw 鍚姩閰嶇疆鍜?runtime-context 浣跨敤鍚屼竴濂楁湁鏁堢綉鍏崇敾鍍?
- [x] 宸叉妸 `phone:agent -- history` 鍐欏叆 OpenClaw 宸ュ叿銆佽兘鍔涘拰璁板繂鎭㈠鏂囨。锛岄伩鍏嶄换鍔″巻鍙茶兘鍔涗笉鍙
- [x] `phone:agent` 榛樿鍙戦€?`max_rounds=60`锛孫penClaw 宸ヤ綔鍖烘枃妗ｅ悓姝ヨ鏄庤疆娆￠绠?
- [x] 榛樿鍚姩璺緞鏀规垚蹇€熸竻鐞嗭細璺宠繃 U 鐩樺己鍒跺啓娴嬨€佽鍒掍换鍔＄粨鏉熷拰 PowerShell CIM 娈嬬暀鎵弿锛岀浉鍏虫參妫€鏌ヤ繚鐣欏湪鐜璇婃柇/涓€閿慨澶?
- [x] 浜戠浼氬憳缃戝叧鏀寔鐢熷浘 / 瑙嗛鐙珛 API Key锛屽鎴风鐢熷浘浼樺厛鍥惧儚 key銆佽棰戜紭鍏堣棰?key锛岀暀绌哄洖閫€閫氱敤 key
- [x] 瀹㈡埛绔細鍛樼綉鍏宠鍙栨敼鎴愪簨瀹炴簮浼樺厛 `gatewayProfile` / 浼氬憳浼氳瘽锛岄伩鍏?license 鏃у€艰鐩栨渶鏂颁笓鐢?key
