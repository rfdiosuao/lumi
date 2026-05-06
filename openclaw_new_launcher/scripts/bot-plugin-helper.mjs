import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

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
    OPENCLAW_CONFIG_PATH: configPath,
    OPENCLAW_HOME: stateDir,
    OPENCLAW_GATEWAY_PORT: process.env.OPENCLAW_GATEWAY_PORT || '18790',
    NO_COLOR: '1',
  };
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

async function install(channelKey) {
  const channel = channels[channelKey];
  if (!channel) fail(`未知插件：${channelKey}`);

  const pkg = assertPackage(channel);
  log(`[launcher] 使用离线插件包：${pkg.name}@${pkg.version}`);
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
  log('[launcher] 准备打开微信扫码绑定，请在下面输出中查看二维码或登录链接。');
  try {
    await runOpenClaw(['channels', 'login', '--channel', 'openclaw-weixin']);
  } catch (error) {
    log('[launcher] 微信扫码命令没有成功结束。如果输出里有 fetch failed，通常是当前网络无法访问微信授权服务，请换网络或稍后再试。');
    throw error;
  }
  log('[launcher] 微信扫码绑定命令已结束。');
}

const [command, channelKey] = process.argv.slice(2);

try {
  if (command === 'install') {
    await install(channelKey);
  } else if (command === 'login-weixin') {
    await loginWeixin();
  } else {
    fail('用法：node scripts/bot-plugin-helper.mjs install feishu|weixin 或 login-weixin');
  }
} catch (error) {
  fail(error?.message || String(error));
}
