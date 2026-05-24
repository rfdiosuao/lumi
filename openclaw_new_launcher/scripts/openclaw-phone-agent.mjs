#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensurePhoneConfig, readLauncherPhoneConfigByDevice, signedJsonRequest } from './openclaw-phone-secure.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, '..');
const DEFAULT_POLL_MS = 1800;
const DEFAULT_TIMEOUT_SEC = 600;
const DEFAULT_MAX_ROUNDS = 60;
const HISTORY_PATH = path.join(PROJECT_ROOT, 'data', '.openclaw', 'logs', 'phone-agent-history.jsonl');

function usage() {
  return `
OpenClaw phone Agent CLI

Usage:
  npm run phone:agent -- run --prompt "读取当前手机屏幕并返回摘要"
  npm run phone:agent -- status --task-id <id>
  npm run phone:agent -- cancel --task-id <id>
  npm run phone:agent -- history --limit 20

Commands:
  run                         Submit one bounded async APKClaw Agent task and wait for the result
  submit                      Submit an async APKClaw Agent task and print the task id
  status                      Read one async task status
  cancel                      Cancel one async task
  history                     Print recent launcher-side phone Agent task history

Run options:
  --prompt <text>              Required for run/submit
  --mode <observe|safe|full>   Default: safe
  --timeout-sec <n>            APKClaw-side timeout. Default: 600, phone clamps to its supported range
  --max-rounds <n>              APKClaw Agent round budget. Default: 60
  --max-wait-sec <n>           CLI wait window for run. Default: 615
  --poll-ms <n>                Poll interval. Default: 1800
  --limit <n>                  History rows to print. Default: 20
  --json                       Print machine-readable JSON

Debug-only options:
  --device-id <id>             Optional. Select one configured APKClaw device from launcher
  --phone-url <url>            Optional. Defaults to launcher Phone Control config
  --phone-token <token>        Optional. Defaults to launcher Phone Control config
`.trim();
}

function parseArgs(argv) {
  const args = {
    command: '',
    prompt: '',
    taskId: '',
    mode: 'safe',
    timeoutSec: DEFAULT_TIMEOUT_SEC,
    maxRounds: DEFAULT_MAX_ROUNDS,
    maxWaitSec: DEFAULT_TIMEOUT_SEC + 15,
    pollMs: DEFAULT_POLL_MS,
    limit: 20,
    deviceId: '',
    phoneUrl: '',
    phoneToken: '',
    json: false,
    help: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = () => {
      const value = argv[i + 1];
      if (!value || value.startsWith('--')) throw new Error(`Missing value for ${arg}`);
      i += 1;
      return value;
    };
    const nextInt = () => {
      const value = Number.parseInt(next(), 10);
      if (!Number.isFinite(value)) throw new Error(`Invalid number for ${arg}`);
      return value;
    };

    switch (arg) {
      case '-h':
      case '--help':
        args.help = true;
        break;
      case '--prompt':
        args.prompt = next();
        break;
      case '--task-id':
        args.taskId = next();
        break;
      case '--mode':
        args.mode = next().toLowerCase();
        break;
      case '--timeout-sec':
        args.timeoutSec = nextInt();
        break;
      case '--max-rounds':
        args.maxRounds = nextInt();
        break;
      case '--max-wait-sec':
        args.maxWaitSec = nextInt();
        break;
      case '--poll-ms':
        args.pollMs = nextInt();
        break;
      case '--limit':
        args.limit = nextInt();
        break;
      case '--device-id':
        args.deviceId = next();
        break;
      case '--phone-url':
        args.phoneUrl = next();
        break;
      case '--phone-token':
        args.phoneToken = next();
        break;
      case '--json':
        args.json = true;
        break;
      default:
        if (!arg.startsWith('-') && !args.command) {
          args.command = arg;
        } else {
          throw new Error(`Unknown option: ${arg}`);
        }
    }
  }

  if (!args.command) args.command = 'run';
  args.command = args.command.toLowerCase();
  args.timeoutSec = Math.max(30, args.timeoutSec);
  args.maxRounds = Math.max(1, args.maxRounds);
  args.maxWaitSec = Math.max(30, args.maxWaitSec);
  args.pollMs = Math.max(500, args.pollMs);
  return args;
}

async function resolveConfig(args) {
  const runtime = await readRuntimeContext();
  const launcherPhone = await readLauncherPhoneConfigByDevice(args.deviceId);
  return {
    ...args,
    phoneUrl: firstNonEmpty(args.phoneUrl, process.env.OPENCLAW_PHONE_BASE_URL, process.env.APKCLAW_BASE_URL, runtime?.phone?.baseUrl, launcherPhone.phoneUrl),
    phoneToken: firstNonEmpty(args.phoneToken, process.env.OPENCLAW_PHONE_TOKEN, process.env.APKCLAW_TOKEN, launcherPhone.phoneToken),
    deviceId: args.deviceId || launcherPhone.id || runtime?.phone?.defaultDeviceId || '',
  };
}

async function readRuntimeContext() {
  const candidates = [
    path.join(PROJECT_ROOT, 'data', '.openclaw', 'workspace', 'runtime-context.json'),
    path.join(PROJECT_ROOT, 'openclaw-workspace', 'runtime-context.json'),
  ];
  for (const filePath of candidates) {
    try {
      return JSON.parse(await fs.readFile(filePath, 'utf8'));
    } catch (error) {
      if (error?.code !== 'ENOENT') throw new Error(`Failed to read ${filePath}: ${error.message}`);
    }
  }
  return {};
}

function firstNonEmpty(...values) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return '';
}

function toolPolicy(mode) {
  if (mode === 'observe' || mode === 'observe_only') return 'observe_only';
  if (mode === 'full' || mode === 'full_access') return 'full_access';
  if (mode === 'safe' || mode === 'safe_action') return 'safe_action';
  throw new Error(`Invalid --mode: ${mode}. Use observe, safe, or full.`);
}

function taskBody(config) {
  const policy = toolPolicy(config.mode);
  return {
    prompt: [
      config.prompt,
      '',
      'OpenClaw wrapper contract:',
      '- Run one bounded task only.',
      `- APKClaw has a hard ${config.maxRounds}-round budget; return partial results instead of looping indefinitely.`,
      '- For shopping/search/list pages, use collect_list_items with a suitable target when available.',
      '- Return structured visible findings, failures, and whether follow-up is needed.',
    ].join('\n'),
    use_template: false,
    force_agent: true,
    learn_template: false,
    read_only: policy === 'observe_only',
    tool_policy: policy,
    template_params: {},
    timeout_sec: config.timeoutSec,
    max_rounds: config.maxRounds,
  };
}

async function submitTask(config) {
  const payload = await signedJsonRequest(config, 'POST', '/api/lumi/agent/tasks', taskBody(config), 60_000);
  const data = payload?.data || payload;
  const taskId = data?.taskId || data?.id;
  if (!taskId) throw new Error('APKClaw did not return a task id.');
  return { payload, taskId };
}

async function getTask(config, taskId) {
  return signedJsonRequest(config, 'GET', `/api/lumi/agent/tasks/${encodeURIComponent(taskId)}`, undefined, 60_000);
}

async function cancelTask(config, taskId) {
  return signedJsonRequest(config, 'POST', `/api/lumi/agent/tasks/${encodeURIComponent(taskId)}/cancel`, {}, 60_000);
}

async function waitForTask(config, taskId) {
  const startedAt = Date.now();
  const maxWaitMs = Math.max(30, config.maxWaitSec) * 1000;
  let lastStatus = null;
  while (Date.now() - startedAt < maxWaitMs) {
    await new Promise((resolve) => setTimeout(resolve, Math.max(500, config.pollMs)));
    const payload = await getTask(config, taskId);
    const data = payload?.data || payload;
    lastStatus = data;
    if (['success', 'error', 'cancelled'].includes(data?.status)) {
      return { payload, task: data };
    }
  }
  return {
    payload: null,
    task: { ...(lastStatus || {}), status: 'error', error: `Timed out waiting for APKClaw task after ${config.maxWaitSec}s` },
  };
}

function summarizeTask(task) {
  const result = task?.result || task?.data || {};
  const answer = result?.answer || task?.answer || '';
  const error = result?.error || task?.error || '';
  const events = Array.isArray(task?.events) ? task.events : Array.isArray(result?.events) ? result.events : [];
  const lastEvent = events.at(-1);
  return [
    `status=${task?.status || 'unknown'}`,
    task?.taskId || task?.id ? `task=${String(task.taskId || task.id).slice(0, 8)}` : '',
    answer ? `answer=${answer}` : '',
    error ? `error=${error}` : '',
    lastEvent?.message ? `last=${lastEvent.message}` : '',
  ].filter(Boolean).join('\n');
}

function classifyFailure(value) {
  const result = value?.result || value?.data || {};
  const parts = [
    value?.status,
    value?.error,
    value?.message,
    result?.error,
    result?.message,
    ...(Array.isArray(value?.events) ? value.events : []),
    ...(Array.isArray(result?.events) ? result.events : []),
  ];
  const text = parts
    .map((item) => (typeof item === 'string' ? item : `${item?.type || ''} ${item?.message || ''} ${item?.error || ''}`))
    .join('\n')
    .toLowerCase();
  if (!text.trim()) return '';
  if (/(401|403|unauthori[sz]ed|forbidden|token|signature|auth)/i.test(text)) return 'unauthorized';
  if (/(accessibility|无障碍|screen.?tree|node tree|permission)/i.test(text)) return 'accessibility_off';
  if (/(timeout|timed out|超时)/i.test(text)) return 'timeout';
  if (/(already running|task is already running|busy|已有任务)/i.test(text)) return 'task_busy';
  if (/(econnrefused|enotfound|network|fetch failed|offline|unreachable|无法连接|离线)/i.test(text)) return 'offline';
  if (/(crash|crashed|崩溃|worker exited|service died|connection reset|socket hang up)/i.test(text)) return 'apkclaw_crash';
  return 'unknown';
}

function promptPreview(prompt) {
  const clean = String(prompt || '').replace(/\s+/g, ' ').trim();
  return clean.length > 160 ? `${clean.slice(0, 160)}...` : clean;
}

function publicDevice(config) {
  return {
    deviceId: config.deviceId || undefined,
    configured: Boolean(config.phoneUrl && config.phoneToken),
  };
}

async function appendHistory(record) {
  try {
    await fs.mkdir(path.dirname(HISTORY_PATH), { recursive: true });
    await fs.appendFile(HISTORY_PATH, `${JSON.stringify({ schema: 'openclaw.phone-agent.history.v1', ...record })}\n`, 'utf8');
  } catch {
    // History must never break a phone task.
  }
}

async function readHistory(limit) {
  try {
    const raw = await fs.readFile(HISTORY_PATH, 'utf8');
    return raw
      .split(/\r?\n/)
      .filter(Boolean)
      .slice(-Math.max(1, Math.min(200, limit || 20)))
      .map((line) => {
        try {
          return JSON.parse(line);
        } catch {
          return { raw: line };
        }
      });
  } catch (error) {
    if (error?.code === 'ENOENT') return [];
    throw error;
  }
}

function print(config, payload, human) {
  if (config.json) console.log(JSON.stringify(payload, null, 2));
  else console.log(human);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(usage());
    return;
  }
  const config = await resolveConfig(args);

  if (config.command === 'history') {
    const rows = await readHistory(config.limit);
    print(
      config,
      { ok: true, historyPath: HISTORY_PATH, count: rows.length, rows },
      rows.length
        ? rows.map((row) => `${row.finishedAt || row.submittedAt || row.createdAt || '-'} ${row.status || row.command || 'unknown'} ${row.taskId ? String(row.taskId).slice(0, 8) : ''} ${row.failureClass || ''} ${row.error || row.summary || ''}`.trim()).join('\n')
        : `No phone Agent history yet.\n${HISTORY_PATH}`,
    );
    return;
  }

  ensurePhoneConfig(config);

  if (config.command === 'submit' || config.command === 'run') {
    if (!config.prompt.trim()) throw new Error('Missing --prompt');
    const submitted = await submitTask(config);
    await appendHistory({
      command: config.command,
      status: 'submitted',
      submittedAt: new Date().toISOString(),
      taskId: submitted.taskId,
      mode: toolPolicy(config.mode),
      timeoutSec: config.timeoutSec,
      maxRounds: config.maxRounds,
      maxWaitSec: config.maxWaitSec,
      promptPreview: promptPreview(config.prompt),
      device: publicDevice(config),
    });
    if (config.command === 'submit') {
      print(config, { ok: true, taskId: submitted.taskId, submitted: submitted.payload }, `submitted task=${submitted.taskId}`);
      return;
    }
    const finalTask = await waitForTask(config, submitted.taskId);
    const ok = finalTask.task?.status === 'success';
    await appendHistory({
      command: config.command,
      status: finalTask.task?.status || 'unknown',
      submittedAt: new Date().toISOString(),
      finishedAt: new Date().toISOString(),
      taskId: submitted.taskId,
      mode: toolPolicy(config.mode),
      timeoutSec: config.timeoutSec,
      maxRounds: config.maxRounds,
      maxWaitSec: config.maxWaitSec,
      promptPreview: promptPreview(config.prompt),
      failureClass: ok ? '' : classifyFailure(finalTask.task),
      error: ok ? '' : (finalTask.task?.result?.error || finalTask.task?.error || ''),
      summary: summarizeTask(finalTask.task),
      device: publicDevice(config),
    });
    print(config, { ok, taskId: submitted.taskId, submitted: submitted.payload, final: finalTask.task }, summarizeTask(finalTask.task));
    return;
  }

  if (config.command === 'status') {
    if (!config.taskId.trim()) throw new Error('Missing --task-id');
    const payload = await getTask(config, config.taskId);
    print(config, payload, summarizeTask(payload?.data || payload));
    return;
  }

  if (config.command === 'cancel') {
    if (!config.taskId.trim()) throw new Error('Missing --task-id');
    const payload = await cancelTask(config, config.taskId);
    await appendHistory({
      command: config.command,
      status: 'cancelled',
      finishedAt: new Date().toISOString(),
      taskId: config.taskId,
      device: publicDevice(config),
    });
    print(config, payload, `cancelled task=${config.taskId.slice(0, 8)}`);
    return;
  }

  throw new Error(`Unknown command: ${config.command}`);
}

main().catch((error) => {
  console.error(`ERROR: ${error?.message || error}`);
  process.exitCode = 1;
});
