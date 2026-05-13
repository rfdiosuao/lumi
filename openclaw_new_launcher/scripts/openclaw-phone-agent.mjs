#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensurePhoneConfig, readLauncherPhoneConfig, signedJsonRequest } from './openclaw-phone-secure.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, '..');
const DEFAULT_POLL_MS = 1800;
const DEFAULT_TIMEOUT_SEC = 600;

function usage() {
  return `
OpenClaw phone Agent CLI

Usage:
  npm run phone:agent -- run --prompt "读取当前手机屏幕并返回摘要"
  npm run phone:agent -- status --task-id <id>
  npm run phone:agent -- cancel --task-id <id>

Commands:
  run                         Submit one bounded async APKClaw Agent task and wait for the result
  submit                      Submit an async APKClaw Agent task and print the task id
  status                      Read one async task status
  cancel                      Cancel one async task

Run options:
  --prompt <text>              Required for run/submit
  --mode <observe|safe|full>   Default: safe
  --timeout-sec <n>            APKClaw-side timeout. Default: 600, phone clamps to its supported range
  --max-wait-sec <n>           CLI wait window for run. Default: 615
  --poll-ms <n>                Poll interval. Default: 1800
  --json                       Print machine-readable JSON

Debug-only options:
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
    maxWaitSec: DEFAULT_TIMEOUT_SEC + 15,
    pollMs: DEFAULT_POLL_MS,
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
      case '--max-wait-sec':
        args.maxWaitSec = nextInt();
        break;
      case '--poll-ms':
        args.pollMs = nextInt();
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
  return args;
}

async function resolveConfig(args) {
  const runtime = await readRuntimeContext();
  const launcherPhone = await readLauncherPhoneConfig();
  return {
    ...args,
    phoneUrl: firstNonEmpty(args.phoneUrl, process.env.OPENCLAW_PHONE_BASE_URL, process.env.APKCLAW_BASE_URL, runtime?.phone?.baseUrl, launcherPhone.phoneUrl),
    phoneToken: firstNonEmpty(args.phoneToken, process.env.OPENCLAW_PHONE_TOKEN, process.env.APKCLAW_TOKEN, launcherPhone.phoneToken),
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
      '- APKClaw has a hard 60-round budget; return partial results instead of looping indefinitely.',
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
  ensurePhoneConfig(config);

  if (config.command === 'submit' || config.command === 'run') {
    if (!config.prompt.trim()) throw new Error('Missing --prompt');
    const submitted = await submitTask(config);
    if (config.command === 'submit') {
      print(config, { ok: true, taskId: submitted.taskId, submitted: submitted.payload }, `submitted task=${submitted.taskId}`);
      return;
    }
    const finalTask = await waitForTask(config, submitted.taskId);
    print(config, { ok: finalTask.task?.status === 'success', taskId: submitted.taskId, submitted: submitted.payload, final: finalTask.task }, summarizeTask(finalTask.task));
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
    print(config, payload, `cancelled task=${config.taskId.slice(0, 8)}`);
    return;
  }

  throw new Error(`Unknown command: ${config.command}`);
}

main().catch((error) => {
  console.error(`ERROR: ${error?.message || error}`);
  process.exitCode = 1;
});
