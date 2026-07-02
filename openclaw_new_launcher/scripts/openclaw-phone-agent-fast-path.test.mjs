import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import http from 'node:http';
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
