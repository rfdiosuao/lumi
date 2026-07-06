import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { spawn } from 'node:child_process';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

test('open-settings template run uses action_fast instead of async Agent task', async () => {
  const seen = [];
  let actionBody = null;
  const server = http.createServer(async (request, response) => {
    seen.push(`${request.method} ${request.url}`);
    const body = await readBody(request);

    if (request.method === 'GET' && request.url === '/api/device/status') {
      return sendJson(response, {
        success: true,
        data: readyStatus({ llmConfigured: true }),
      });
    }
    if (request.method === 'POST' && request.url === '/api/lumi/security/pair') {
      return sendJson(response, {
        success: true,
        data: { launcherId: 'test-launcher', launcherSecret: 'test-secret' },
      });
    }
    if (request.method === 'POST' && request.url.startsWith('/api/lumi/agent/action_fast')) {
      actionBody = JSON.parse(body || '{}');
      return sendJson(response, {
        success: true,
        data: {
          mode: 'action_fast',
          action: 'open_app',
          currentStep: 'complete',
          summary: 'Settings',
          currentPackage: 'com.android.settings',
          screenHash: 'hash-after-open-settings',
          beforeHash: 'hash-before-open-settings',
          afterHash: 'hash-after-open-settings',
          changed: true,
          actionMs: 11,
          verifyMs: 17,
          metrics: { mode: 'action_fast', totalMs: 24, rounds: 0 },
          events: [{ type: 'action_fast_completed', success: true }],
        },
      });
    }
    if (request.method === 'POST' && request.url === '/api/lumi/agent/tasks') {
      return sendJson(response, { success: false, error: 'async_agent_should_not_be_called' }, 500);
    }

    return sendJson(response, { success: false, error: `unexpected ${request.method} ${request.url}` }, 404);
  });

  await listen(server);
  try {
    const port = server.address().port;
    const result = await runCli([
      'run',
      '--phone-url',
      `http://127.0.0.1:${port}`,
      '--phone-token',
      'test-token',
      '--execution-layer',
      'template',
      '--template',
      'open-settings',
      '--daemon',
      'off',
      '--prompt',
      '打开系统设置',
      '--json',
      '--step-timeout-sec',
      '5',
      '--timeout-sec',
      '30',
      '--max-wait-sec',
      '30',
    ]);

    assert.equal(result.code, 0, result.stderr);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.ok, true);
    assert.equal(payload.mode, 'action_fast');
    assert.equal(payload.metrics.rounds, 0);
    assert.equal(payload.screenHash, 'hash-after-open-settings');
    assert.equal(payload.beforeHash, 'hash-before-open-settings');
    assert.equal(payload.afterHash, 'hash-after-open-settings');
    assert.equal(payload.changed, true);
    assert.equal(payload.actionMs, 11);
    assert.equal(payload.verifyMs, 17);
    assert.equal(payload.currentPackage, 'com.android.settings');
    assert.equal(actionBody.action, 'open_app');
    assert.equal(actionBody.packageName, 'com.android.settings');
    assert.equal(actionBody.verifyForeground, true);
    assert.equal(seen.includes('POST /api/lumi/agent/tasks'), false);
    assert.equal(seen.some((line) => line.startsWith('POST /api/lumi/agent/action_fast')), true);
  } finally {
    await close(server);
  }
});

test('read-screen template run uses observe_fast without requiring an LLM model', async () => {
  const seen = [];
  const server = http.createServer(async (request, response) => {
    seen.push(`${request.method} ${request.url}`);
    await readBody(request);

    if (request.method === 'GET' && request.url === '/api/device/status') {
      return sendJson(response, {
        success: true,
        data: readyStatus({ llmConfigured: false, modelConfigured: false, modelReady: false }),
      });
    }
    if (request.method === 'POST' && request.url === '/api/lumi/security/pair') {
      return sendJson(response, {
        success: true,
        data: { launcherId: 'test-launcher', launcherSecret: 'test-secret' },
      });
    }
    if (request.method === 'GET' && request.url === '/api/lumi/agent/observe_fast?_lumi=1') {
      return sendJson(response, {
        success: true,
        data: {
          mode: 'observe_fast',
          summary: 'Home screen',
          currentPackage: 'com.example.home',
          screenHash: 'hash-fast',
          metrics: { mode: 'observe_fast', totalMs: 12, rounds: 0 },
        },
      });
    }
    if (request.method === 'POST' && request.url === '/api/lumi/agent/tasks') {
      return sendJson(response, { success: false, error: 'async_agent_should_not_be_called' }, 500);
    }

    return sendJson(response, { success: false, error: `unexpected ${request.method} ${request.url}` }, 404);
  });

  await listen(server);
  try {
    const port = server.address().port;
    const result = await runCli([
      'run',
      '--phone-url',
      `http://127.0.0.1:${port}`,
      '--phone-token',
      'test-token',
      '--execution-layer',
      'template',
      '--template',
      'read-screen',
      '--daemon',
      'off',
      '--prompt',
      '读取当前屏幕',
      '--json',
      '--step-timeout-sec',
      '5',
      '--timeout-sec',
      '30',
      '--max-wait-sec',
      '30',
    ]);

    assert.equal(result.code, 0, result.stderr);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.ok, true);
    assert.equal(payload.mode, 'observe_fast');
    assert.equal(payload.stalePossible, true);
    assert.equal(payload.metrics.rounds, 0);
    assert.equal(payload.currentStep, 'success');
    assert.equal(seen.includes('POST /api/lumi/agent/tasks'), false);
    assert.equal(seen.includes('GET /api/lumi/agent/observe_fast?_lumi=1'), true);
  } finally {
    await close(server);
  }
});

test('parallel explicit CLI calls reuse the same generated Lumi launcher id', async () => {
  const launcherIds = [];
  let activeActions = 0;
  let maxActiveActions = 0;
  const server = http.createServer(async (request, response) => {
    const body = await readBody(request);

    if (request.method === 'GET' && request.url === '/api/device/status') {
      return sendJson(response, {
        success: true,
        data: readyStatus({ llmConfigured: true }),
      });
    }
    if (request.method === 'POST' && request.url === '/api/lumi/security/pair') {
      const parsed = JSON.parse(body || '{}');
      launcherIds.push(parsed.launcherId);
      return sendJson(response, {
        success: true,
        data: { launcherId: parsed.launcherId, launcherSecret: 'shared-secret' },
      });
    }
    if (request.method === 'POST' && request.url.startsWith('/api/lumi/agent/action_fast')) {
      activeActions += 1;
      maxActiveActions = Math.max(maxActiveActions, activeActions);
      await delay(120);
      activeActions -= 1;
      return sendJson(response, {
        success: true,
        data: {
          mode: 'action_fast',
          currentStep: 'complete',
          metrics: { mode: 'action_fast', totalMs: 10, rounds: 0 },
        },
      });
    }

    return sendJson(response, { success: false, error: `unexpected ${request.method} ${request.url}` }, 404);
  });

  await listen(server);
  try {
    const port = server.address().port;
    const baseArgs = [
      'run',
      '--phone-url',
      `http://127.0.0.1:${port}`,
      '--phone-token',
      'test-token',
      '--execution-layer',
      'template',
      '--template',
      'open-settings',
      '--daemon',
      'off',
      '--prompt',
      '打开系统设置',
      '--json',
      '--step-timeout-sec',
      '5',
      '--timeout-sec',
      '30',
      '--max-wait-sec',
      '30',
    ];

    const results = await Promise.all([runCli(baseArgs), runCli(baseArgs)]);

    assert.equal(results[0].code, 0, results[0].stderr);
    assert.equal(results[1].code, 0, results[1].stderr);
    assert.equal(launcherIds.length, 2);
    assert.equal(new Set(launcherIds).size, 1);
    assert.equal(maxActiveActions, 1);
  } finally {
    await close(server);
  }
});

test('unreachable phone url returns structured LAN Config guidance', async () => {
  const port = await unusedPort();
  const result = await runCli([
    'metrics',
    '--daemon',
    'off',
    '--phone-url',
    `http://127.0.0.1:${port}`,
    '--phone-token',
    'test-token',
    '--json',
    '--step-timeout-sec',
    '5',
  ]);

  assert.notEqual(result.code, 0);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.ok, false);
  assert.equal(payload.errorCode, 'phone_config_server_unreachable');
  assert.match(payload.message, /APKClaw ConfigServer/);
  assert.match(payload.remediation.join('\n'), /APKClaw -> Settings -> LAN Config/);
});

test('vision action supports PowerShell-safe action body file', async () => {
  let actionBody = null;
  const server = http.createServer(async (request, response) => {
    const body = await readBody(request);
    if (request.method === 'POST' && request.url === '/api/lumi/security/pair') {
      const parsed = JSON.parse(body || '{}');
      return sendJson(response, {
        success: true,
        data: { launcherId: parsed.launcherId, launcherSecret: 'vision-secret' },
      });
    }
    if (request.method === 'POST' && request.url.startsWith('/api/lumi/agent/action_fast')) {
      actionBody = JSON.parse(body || '{}');
      return sendJson(response, {
        success: true,
        data: {
          mode: 'action_fast',
          action: actionBody.action,
          currentStep: 'complete',
          metrics: { mode: 'action_fast', totalMs: 9, rounds: 0 },
        },
      });
    }
    return sendJson(response, { success: false, error: `unexpected ${request.method} ${request.url}` }, 404);
  });

  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'loom-vision-body-'));
  await listen(server);
  try {
    const bodyPath = path.join(tmpDir, 'action.json');
    await fs.writeFile(bodyPath, JSON.stringify({
      action: 'tap',
      gridCell: 'C7',
      targetLabel: 'settings button',
      reason: 'open settings',
    }), 'utf8');
    const port = server.address().port;
    const result = await runVisionCli([
      'action',
      '--force-action',
      '--fast-path',
      'action_fast',
      '--phone-url',
      `http://127.0.0.1:${port}`,
      '--phone-token',
      'test-token',
      '--action-body-file',
      bodyPath,
      '--json',
    ]);

    assert.equal(result.code, 0, result.stderr);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.success, true);
    assert.equal(actionBody.action, 'tap');
    assert.equal(actionBody.gridCell, 'C7');
  } finally {
    await close(server);
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test('wechat-reply command calls signed safe auto reply endpoint', async () => {
  let requestBody = null;
  const server = http.createServer(async (request, response) => {
    const body = await readBody(request);
    if (request.method === 'POST' && request.url === '/api/lumi/security/pair') {
      const parsed = JSON.parse(body || '{}');
      return sendJson(response, {
        success: true,
        data: { launcherId: parsed.launcherId, launcherSecret: 'wechat-secret' },
      });
    }
    if (request.method === 'POST' && request.url === '/api/lumi/wechat/auto_reply') {
      requestBody = JSON.parse(body || '{}');
      return sendJson(response, {
        success: true,
        data: {
          mode: 'wechat_auto_reply',
          currentStep: 'drafted',
          contact: 'Alice',
          latestMessage: 'hello',
          replyText: requestBody.replyText,
          autoSend: requestBody.autoSend,
          sent: false,
        },
      });
    }
    return sendJson(response, { success: false, error: `unexpected ${request.method} ${request.url}` }, 404);
  });

  await listen(server);
  try {
    const port = server.address().port;
    const result = await runCli([
      'wechat-reply',
      '--phone-url',
      `http://127.0.0.1:${port}`,
      '--phone-token',
      'test-token',
      '--reply',
      '你好，我稍后回复你',
      '--json',
    ]);

    assert.equal(result.code, 0, result.stderr);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.ok, true);
    assert.equal(payload.mode, 'wechat_auto_reply');
    assert.equal(payload.currentStep, 'drafted');
    assert.equal(requestBody.replyText, '你好，我稍后回复你');
    assert.equal(requestBody.autoSend, false);
  } finally {
    await close(server);
  }
});

test('task events command polls task-specific Lumi events endpoint', async () => {
  const seen = [];
  const server = http.createServer(async (request, response) => {
    seen.push(`${request.method} ${request.url}`);
    await readBody(request);

    if (request.method === 'GET' && request.url === '/api/device/status') {
      return sendJson(response, { success: true, data: readyStatus({ llmConfigured: true }) });
    }
    if (request.method === 'POST' && request.url === '/api/lumi/security/pair') {
      return sendJson(response, {
        success: true,
        data: { launcherId: 'test-launcher', launcherSecret: 'test-secret' },
      });
    }
    if (request.method === 'GET' && request.url === '/api/lumi/agent/tasks/task-123/events') {
      return sendJson(response, {
        success: true,
        data: {
          taskId: 'task-123',
          status: 'running',
          cancelRequested: false,
          events: [{ type: 'tool_call', round: 1, message: 'Open App' }],
        },
      });
    }

    return sendJson(response, { success: false, error: `unexpected ${request.method} ${request.url}` }, 404);
  });

  await listen(server);
  try {
    const port = server.address().port;
    const result = await runCli([
      'events',
      '--phone-url',
      `http://127.0.0.1:${port}`,
      '--phone-token',
      'test-token',
      '--task-id',
      'task-123',
      '--daemon',
      'off',
      '--json',
    ]);

    assert.equal(result.code, 0, result.stderr);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.success, true);
    assert.equal(payload.data.taskId, 'task-123');
    assert.equal(payload.data.events[0].type, 'tool_call');
    assert.equal(seen.includes('GET /api/lumi/agent/tasks/task-123/events'), true);
  } finally {
    await close(server);
  }
});

function readyStatus(overrides = {}) {
  return {
    busy: false,
    queueSupported: true,
    accessibilityState: 'healthy',
    accessibilityHealthy: true,
    accessibilityRunning: true,
    screenOn: true,
    interactive: true,
    deviceLocked: false,
    agentInitialized: true,
    llmConfigured: true,
    modelConfigured: true,
    modelReady: true,
    ...overrides,
  };
}

function runCli(args) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, ['scripts/openclaw-phone-agent.mjs', ...args], {
      cwd: new URL('..', import.meta.url),
      env: {
        ...process.env,
        NO_COLOR: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('close', (code) => {
      resolve({ code, stdout, stderr });
    });
  });
}

function runVisionCli(args) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, ['scripts/openclaw-phone-vision.mjs', ...args], {
      cwd: new URL('..', import.meta.url),
      env: {
        ...process.env,
        NO_COLOR: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('close', (code) => {
      resolve({ code, stdout, stderr });
    });
  });
}

async function unusedPort() {
  const server = http.createServer();
  await listen(server);
  const port = server.address().port;
  await close(server);
  return port;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    let body = '';
    request.setEncoding('utf8');
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => resolve(body));
    request.on('error', reject);
  });
}

function sendJson(response, payload, status = 200) {
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  response.end(JSON.stringify(payload));
}

function listen(server) {
  return new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
}

function close(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
}
