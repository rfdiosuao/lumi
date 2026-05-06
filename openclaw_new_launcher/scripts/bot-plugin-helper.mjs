import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const rootDir = process.cwd();
const nodeExe = process.execPath;
const openclawMjs = path.join(rootDir, 'node_modules', 'openclaw', 'openclaw.mjs');
const stateDir = process.env.OPENCLAW_STATE_DIR || path.join(rootDir, 'data', '.openclaw');
const configPath = process.env.OPENCLAW_CONFIG_PATH || path.join(stateDir, 'openclaw.json');
const extensionsDir = path.join(stateDir, 'extensions');

const channels = {
  feishu: {
    title: '飞书机器人',
    pluginId: 'openclaw-lark',
    packageName: '@larksuite/openclaw-lark',
    packageDir: path.join(rootDir, 'node_modules', '@larksuite', 'openclaw-lark'),
  },
  weixin: {
    title: '微信机器人',
    pluginId: 'openclaw-weixin',
    packageName: '@tencent-weixin/openclaw-weixin',
    packageDir: path.join(rootDir, 'node_modules', '@tencent-weixin', 'openclaw-weixin'),
  },
};

function log(message = '') {
  process.stdout.write(`${message}\n`);
}

function fail(message) {
  process.stderr.write(`[launcher] ${message}\n`);
  process.exit(1);
}

function readJson(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
}

function assertPackage(channel) {
  const pkgPath = path.join(channel.packageDir, 'package.json');
  if (!fs.existsSync(pkgPath)) {
    fail(`离线包里缺少 ${channel.packageName}，请重新打包后再安装。`);
  }

  const pkg = readJson(pkgPath, null);
  if (!pkg || pkg.name !== channel.packageName) {
    fail(`插件包校验失败：${pkgPath}`);
  }

  return pkg;
}

function removeExistingLink(linkPath) {
  if (!fs.existsSync(linkPath)) return;

  const stat = fs.lstatSync(linkPath);
  if (stat.isSymbolicLink() || stat.isDirectory() || stat.isFile()) {
    fs.rmSync(linkPath, { recursive: true, force: true });
  }
}

function ensureExtensionEntry(channel) {
  fs.mkdirSync(extensionsDir, { recursive: true });
  const linkPath = path.join(extensionsDir, channel.pluginId);
  const currentPkg = readJson(path.join(linkPath, 'package.json'), null);
  if (currentPkg?.name === channel.packageName) {
    log(`[launcher] 扩展目录已存在：${linkPath}`);
    return linkPath;
  }

  removeExistingLink(linkPath);
  try {
    fs.symlinkSync(channel.packageDir, linkPath, 'junction');
    log(`[launcher] 已链接扩展目录：${linkPath}`);
  } catch (error) {
    log(`[launcher] 创建目录链接失败，改为复制插件文件：${error.message}`);
    fs.cpSync(channel.packageDir, linkPath, { recursive: true, force: true });
  }
  return linkPath;
}

function updateOpenClawConfig(channel) {
  const data = readJson(configPath, {});
  data.gateway ||= {};
  data.gateway.auth ||= {};
  data.gateway.auth.mode ||= 'none';
  data.gateway.bind ||= 'loopback';

  data.plugins ||= {};
  data.plugins.load ||= {};
  data.plugins.load.paths = Array.isArray(data.plugins.load.paths)
    ? data.plugins.load.paths
    : [];

  const normalizedPackageDir = path.resolve(channel.packageDir);
  const hasPath = data.plugins.load.paths.some((item) => (
    path.resolve(rootDir, String(item)).toLowerCase() === normalizedPackageDir.toLowerCase()
  ));
  if (!hasPath) {
    data.plugins.load.paths.push(normalizedPackageDir);
  }

  data.plugins.entries ||= {};
  data.plugins.entries[channel.pluginId] = {
    ...(data.plugins.entries[channel.pluginId] || {}),
    enabled: true,
  };

  writeJson(configPath, data);
  log(`[launcher] 已写入 OpenClaw 配置：${configPath}`);
}

function openclawEnv() {
  const nodeDir = path.join(rootDir, 'node');
  const binDir = path.join(rootDir, 'node_modules', '.bin');
  const currentPath = process.env.Path || process.env.PATH || '';
  return {
    ...process.env,
    PATH: `${nodeDir}${path.delimiter}${binDir}${path.delimiter}${currentPath}`,
    Path: `${nodeDir}${path.delimiter}${binDir}${path.delimiter}${currentPath}`,
    OPENCLAW_STATE_DIR: stateDir,
    OPENCLAW_CONFIG: configPath,
    OPENCLAW_CONFIG_PATH: configPath,
    OPENCLAW_HOME: stateDir,
    OPENCLAW_GATEWAY_PORT: process.env.OPENCLAW_GATEWAY_PORT || '18790',
    NO_COLOR: '1',
  };
}

function patchWeixinFetchHeaders(channel) {
  if (channel.pluginId !== 'openclaw-weixin') return;

  const apiFile = path.join(channel.packageDir, 'dist', 'src', 'api', 'api.js');
  if (!fs.existsSync(apiFile)) return;

  const source = fs.readFileSync(apiFile, 'utf8');
  const patched = source.replace(
    /\s*"Content-Length": String\(Buffer\.byteLength\(opts\.body, "utf-8"\)\),\r?\n/,
    '\n',
  );

  if (patched !== source) {
    fs.writeFileSync(apiFile, patched, 'utf8');
    log('[launcher] 已修复微信插件 fetch 请求头兼容问题。');
  }
}

function runOpenClaw(args) {
  if (!fs.existsSync(openclawMjs)) {
    fail(`找不到 OpenClaw 本体：${openclawMjs}`);
  }

  return new Promise((resolve, reject) => {
    const child = spawn(nodeExe, [openclawMjs, ...args], {
      cwd: rootDir,
      env: openclawEnv(),
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    child.stdout.on('data', (chunk) => process.stdout.write(chunk));
    child.stderr.on('data', (chunk) => process.stderr.write(chunk));
    child.on('error', reject);
    child.on('close', (code, signal) => {
      if (signal) {
        reject(new Error(`OpenClaw 命令被终止：${signal}`));
        return;
      }
      if (code !== 0) {
        reject(new Error(`OpenClaw 命令退出码：${code}`));
        return;
      }
      resolve();
    });
  });
}

function importFile(filePath) {
  return import(pathToFileURL(filePath).href);
}

async function install(channelKey) {
  const channel = channels[channelKey];
  if (!channel) fail(`未知插件：${channelKey}`);

  const pkg = assertPackage(channel);
  log(`[launcher] 使用离线插件包：${pkg.name}@${pkg.version}`);
  patchWeixinFetchHeaders(channel);
  ensureExtensionEntry(channel);
  updateOpenClawConfig(channel);

  try {
    log('[launcher] 刷新 OpenClaw 插件索引...');
    await runOpenClaw(['plugins', 'registry', '--refresh']);
  } catch (error) {
    log(`[launcher] 插件索引刷新未完成，可在重启核心服务后自动生效：${error.message}`);
  }

  log(`[launcher] ${channel.title}插件已安装到本地配置。`);
}

async function loginWeixin() {
  await install('weixin');

  const channel = channels.weixin;
  const loginQr = await importFile(path.join(channel.packageDir, 'dist', 'src', 'auth', 'login-qr.js'));
  const accounts = await importFile(path.join(channel.packageDir, 'dist', 'src', 'auth', 'accounts.js'));
  const inbound = await importFile(path.join(channel.packageDir, 'dist', 'src', 'messaging', 'inbound.js'));
  const accountIdModule = await importFile(path.join(rootDir, 'node_modules', 'openclaw', 'dist', 'plugin-sdk', 'account-id.js'));

  log('[launcher] 准备打开微信扫码绑定，请在下面输出中查看二维码或登录链接。');
  const startResult = await loginQr.startWeixinLoginWithQr({
    botType: loginQr.DEFAULT_ILINK_BOT_TYPE || '3',
    force: true,
    verbose: true,
  });

  if (!startResult.qrcodeUrl) {
    throw new Error(startResult.message || '微信二维码获取失败');
  }

  log('\n用手机微信扫描以下二维码，以继续连接：\n');
  await loginQr.displayQRCode(startResult.qrcodeUrl);
  log('\n正在等待扫码确认。完成后会自动写入本地配置；如果暂时不绑定，可以点击“停止命令”。\n');

  const waitResult = await loginQr.waitForWeixinLogin({
    sessionKey: startResult.sessionKey,
    timeoutMs: 480_000,
    verbose: true,
    botType: loginQr.DEFAULT_ILINK_BOT_TYPE || '3',
  });

  if (waitResult.connected && waitResult.botToken && waitResult.accountId) {
    const normalizedId = accountIdModule.normalizeAccountId(waitResult.accountId);
    accounts.saveWeixinAccount(normalizedId, {
      token: waitResult.botToken,
      baseUrl: waitResult.baseUrl,
      userId: waitResult.userId,
    });
    accounts.registerWeixinAccountId(normalizedId);
    if (waitResult.userId) {
      accounts.clearStaleAccountsForUserId(normalizedId, waitResult.userId, inbound.clearContextTokensForAccount);
    }
    await accounts.triggerWeixinChannelReload();
    log('\n[launcher] 微信扫码绑定成功，账号数据已写入 OpenClaw 配置。');
    return;
  }

  throw new Error(waitResult.message || '微信扫码绑定未完成');
}

async function printQrCode(url) {
  try {
    const qrcode = await import('qrcode-terminal');
    qrcode.default.generate(url, { small: true });
  } catch {
    log('[launcher] 二维码渲染组件不可用，请复制下面链接打开：');
  }
  log(url);
}

async function postFeishuForm(baseUrl, params) {
  const body = new URLSearchParams(params).toString();
  const response = await fetch(`${baseUrl}/oauth/v1/app/registration`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`Feishu auth ${response.status}: ${text}`);
  }
  if (!response.ok) {
    if (data?.error) return data;
    throw new Error(`Feishu auth ${response.status}: ${text}`);
  }
  return data;
}

async function loginFeishu() {
  await install('feishu');

  let baseUrl = 'https://accounts.feishu.cn';
  log('[launcher] 正在向飞书申请扫码配置二维码...');
  const init = await postFeishuForm(baseUrl, { action: 'init' });
  if (Array.isArray(init.supported_auth_methods) && !init.supported_auth_methods.includes('client_secret')) {
    fail('当前飞书环境不支持 client_secret 授权，请改用手动 App ID/App Secret 配置。');
  }

  const begin = await postFeishuForm(baseUrl, {
    action: 'begin',
    archetype: 'PersonalAgent',
    auth_method: 'client_secret',
    request_user_info: 'open_id',
  });

  const qrUrl = new URL(begin.verification_uri_complete);
  qrUrl.searchParams.set('from', 'onboard');
  const qrUrlText = qrUrl.toString();
  log('[launcher] 请使用飞书扫码配置机器人，或复制二维码下方链接打开。');
  await printQrCode(qrUrlText);

  const startedAt = Date.now();
  let intervalSeconds = Number(begin.interval || 5);
  const expireSeconds = Number(begin.expire_in || 600);
  let domain = 'feishu';
  let switchedDomain = false;

  while (Date.now() - startedAt < expireSeconds * 1000) {
    await new Promise((resolve) => setTimeout(resolve, intervalSeconds * 1000));
    const poll = await postFeishuForm(baseUrl, {
      action: 'poll',
      device_code: begin.device_code,
    });

    if (poll.user_info?.tenant_brand === 'lark' && !switchedDomain) {
      baseUrl = 'https://accounts.larksuite.com';
      domain = 'lark';
      switchedDomain = true;
      log('[launcher] 检测到 Lark 租户，已切换到 Lark 授权域名继续轮询。');
      continue;
    }

    if (poll.client_id && poll.client_secret) {
      const data = readJson(configPath, {});
      data.channels ||= {};
      const channelConfig = {
        enabled: true,
        appId: poll.client_id,
        appSecret: poll.client_secret,
        domain,
        connectionMode: 'websocket',
        requireMention: true,
        dmPolicy: poll.user_info?.open_id ? 'allowlist' : 'open',
        allowFrom: poll.user_info?.open_id ? [poll.user_info.open_id] : [],
        groupPolicy: 'open',
        groupAllowFrom: [],
      };
      data.channels.feishu = channelConfig;
      data.channels['openclaw-lark'] = channelConfig;
      data.plugins ||= {};
      data.plugins.allow = Array.isArray(data.plugins.allow) ? data.plugins.allow : [];
      if (!data.plugins.allow.includes('openclaw-lark')) data.plugins.allow.push('openclaw-lark');
      data.plugins.entries ||= {};
      data.plugins.entries['openclaw-lark'] = {
        ...(data.plugins.entries['openclaw-lark'] || {}),
        enabled: true,
      };
      writeJson(configPath, data);
      log('[launcher] 飞书扫码配置成功，App ID/App Secret 已写入 OpenClaw 配置。');
      return;
    }

    if (poll.error === 'authorization_pending') {
      process.stdout.write('.');
      continue;
    }

    if (poll.error === 'slow_down') {
      intervalSeconds += 5;
      log(`[launcher] 飞书要求降低轮询频率，调整为 ${intervalSeconds}s。`);
      continue;
    }

    if (poll.error) {
      throw new Error(`${poll.error}: ${poll.error_description || ''}`.trim());
    }
  }

  throw new Error('飞书扫码配置超时，请重新点击安装或改用手动 App ID/App Secret。');
}

const [command, channelKey] = process.argv.slice(2);

try {
  if (command === 'install') {
    await install(channelKey);
  } else if (command === 'login-feishu') {
    await loginFeishu();
  } else if (command === 'login-weixin') {
    await loginWeixin();
  } else {
    fail('用法：node scripts/bot-plugin-helper.mjs install feishu|weixin 或 login-feishu 或 login-weixin');
  }
} catch (error) {
  fail(error?.message || String(error));
}
