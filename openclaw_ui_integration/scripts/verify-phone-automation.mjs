import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve('D:\\Axiangmu\\AUSTART\\openclaw_ui_integration');
const sourcePath = path.join(root, 'src', 'redesign', 'lib', 'phoneAutomation.ts');
const reportPath = path.join(root, 'data', 'logs', 'phone-automation-smoke.json');

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function importPhoneAutomationModule() {
  const source = await fs.readFile(sourcePath, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      isolatedModules: true,
    },
    fileName: sourcePath,
  }).outputText;
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'openclaw-phone-automation-'));
  const tempPath = path.join(tempDir, 'phoneAutomation.mjs');
  await fs.writeFile(tempPath, output, 'utf8');
  return import(`${pathToFileURL(tempPath).href}?t=${Date.now()}`);
}

const mod = await importPhoneAutomationModule();
const requiredExports = [
  'builtInAutomationTemplates',
  'createAutomationId',
  'createDefaultAutomationState',
  'normalizeAutomationState',
  'applyTemplateVariables',
  'automationRiskLabel',
  'automationStatusLabel',
];

for (const key of requiredExports) {
  assert(typeof mod[key] === 'function', `missing export: ${key}`);
}

const templates = mod.builtInAutomationTemplates();
const templateById = new Map(templates.map((template) => [template.id, template]));
const requiredTemplateIds = [
  'xianyu-polish',
  'xianyu-checkin',
  'xianyu-listing-inspection',
  'xianyu-message-snapshot',
  'xianyu-exposure',
  'xianyu-earn-exposure',
  'xianyu-publish-dry-run',
  'xianyu-bargain-dry-run',
  'xianyu-ad-exposure-dry-run',
  'generic-screen-check',
  'generic-open-app-snapshot',
];

for (const id of requiredTemplateIds) {
  assert(templateById.has(id), `missing template: ${id}`);
}

const highRiskIds = [
  'xianyu-exposure',
  'xianyu-publish-dry-run',
  'xianyu-bargain-dry-run',
  'xianyu-ad-exposure-dry-run',
];

for (const template of templates) {
  assert(template.title && template.prompt, `template ${template.id} lacks title or prompt`);
  assert(['dry-run', 'safe'].includes(template.mode), `template ${template.id} has invalid mode`);
  assert(['low', 'medium', 'high'].includes(template.riskLevel), `template ${template.id} has invalid riskLevel`);
  assert(Array.isArray(template.variables), `template ${template.id} variables must be array`);
  const rendered = mod.applyTemplateVariables(template);
  assert(!/{{\s*[\w.-]+\s*}}/.test(rendered), `template ${template.id} leaves unresolved variables`);
  if (template.packId === 'xianyu') {
    assert(/不要|禁止|停止|确认前|dry-run/.test(template.prompt), `xianyu template ${template.id} must include a safety boundary`);
    assert(/截图|节点树|返回|读取/.test(template.prompt), `xianyu template ${template.id} must request observable evidence`);
  }
  if (highRiskIds.includes(template.id)) {
    assert(template.mode === 'dry-run', `high risk template ${template.id} must be dry-run`);
    assert(template.riskLevel === 'high', `high risk template ${template.id} must be marked high`);
    assert(template.requiresManualConfirmation === true, `high risk template ${template.id} must require confirmation`);
    assert(/禁止点击|禁止选择|禁止上传|必须停在确认前|进入表单后立即停止|立即停止/.test(template.prompt), `high risk template ${template.id} must stop before final action`);
  }
}

const exposureTemplate = templateById.get('xianyu-exposure');
assert(/暂无可加曝光的宝贝/.test(exposureTemplate.prompt), 'exposure template must handle no eligible item state');
assert(/开始曝光|确认使用|加曝光确认/.test(exposureTemplate.prompt), 'exposure template must block final exposure actions');

const polishTemplate = templateById.get('xianyu-polish');
assert(polishTemplate.title === '闲鱼一键擦亮', 'polish template title must stay focused');
assert(/固定链路/.test(polishTemplate.prompt), 'polish template must be a fixed path');
assert(/打开闲鱼/.test(polishTemplate.prompt), 'polish template must open xianyu first');
assert(/底部导航「我的」/.test(polishTemplate.prompt), 'polish template must click 我的');
assert(/点击「我发布的」/.test(polishTemplate.prompt), 'polish template must click 我发布的');
assert(/一键擦亮\/今日擦亮\/擦亮\/立即擦亮/.test(polishTemplate.prompt), 'polish template must click only explicit polish labels');
assert(/商品推荐/.test(polishTemplate.prompt) && /一键转卖/.test(polishTemplate.prompt), 'polish template must avoid recommendation/resell areas');
assert(/不要进入曝光/.test(polishTemplate.prompt) && /发闲置/.test(polishTemplate.prompt), 'polish template must avoid exposure and publish branches');

const publishTemplate = templateById.get('xianyu-publish-dry-run');
assert(/右上角「发布」/.test(publishTemplate.prompt), 'publish template must block final publish button');
assert(/选择图片|上传素材|填写标题/.test(publishTemplate.prompt), 'publish template must block form mutation');

const now = new Date().toISOString();
const xianyuTemplate = templateById.get('xianyu-polish');
const scheduleId = mod.createAutomationId('smoke-schedule');
const queueId = mod.createAutomationId('smoke-queue');
const fixture = mod.normalizeAutomationState({
  schema: 'openclaw.launcher.phone-automation.v1',
  updatedAt: now,
  templates,
  schedules: [{
    id: scheduleId,
    label: 'Smoke 闲鱼擦亮',
    templateId: xianyuTemplate.id,
    deviceIds: ['fixture-phone'],
    cadence: '每天 09:30',
    timeWindow: '09:00-10:30',
    mode: 'dry-run',
    enabled: true,
    createdAt: now,
    updatedAt: now,
    nextRunHint: 'fixture',
  }],
  queue: [{
    id: queueId,
    scheduleId,
    templateId: xianyuTemplate.id,
    deviceIds: ['fixture-phone'],
    status: 'running',
    createdAt: now,
    updatedAt: now,
    mode: 'dry-run',
    result: 'fixture running',
  }],
  logs: [
    {
      id: mod.createAutomationId('smoke-log'),
      queueId,
      scheduleId,
      templateId: xianyuTemplate.id,
      templateTitle: xianyuTemplate.title,
      deviceId: 'fixture-phone',
      deviceName: 'fixture phone',
      status: 'success',
      mode: 'dry-run',
      queuedAt: now,
      startedAt: now,
      finishedAt: now,
      result: 'fixture ok',
      screenshotPath: 'data/.openclaw/automation/screenshots/smoke.png',
    },
    {
      id: mod.createAutomationId('smoke-log'),
      queueId,
      scheduleId,
      templateId: xianyuTemplate.id,
      templateTitle: xianyuTemplate.title,
      deviceId: 'fixture-phone',
      deviceName: 'fixture phone',
      status: 'failed',
      mode: 'dry-run',
      queuedAt: now,
      startedAt: now,
      finishedAt: now,
      failureReason: 'fixture_failure_for_ui_check',
    },
  ],
});

assert(fixture.schedules.length === 1, 'schedule fixture was not retained');
assert(fixture.queue.length === 1 && fixture.queue[0].status === 'running', 'queue fixture was not retained');
assert(fixture.logs.length === 2, 'log fixture was not retained');
assert(fixture.logs.some((log) => log.status === 'failed' && log.failureReason), 'failed log fixture missing failure reason');
assert(mod.automationRiskLabel('medium') === '需确认', 'risk label mapping failed');
assert(mod.automationStatusLabel('failed') === '失败', 'status label mapping failed');

const report = {
  verifiedAt: now,
  source: path.relative(root, sourcePath),
  templateCount: templates.length,
  xianyuTemplateIds: templates.filter((template) => template.packId === 'xianyu').map((template) => template.id),
  genericTemplateIds: templates.filter((template) => template.packId === 'generic').map((template) => template.id),
  highRiskIds,
  fixture: {
    schedules: fixture.schedules.length,
    queue: fixture.queue.length,
    logs: fixture.logs.length,
    failedLogVisible: fixture.logs.some((log) => log.status === 'failed' && log.failureReason),
  },
  safety: {
    realDeviceTouched: false,
    realXianyuActionTouched: false,
    finalPublishBlocked: true,
    finalExposureBlocked: true,
  },
};

await fs.mkdir(path.dirname(reportPath), { recursive: true });
await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(`[automation-smoke] ok templates=${report.templateCount} xianyu=${report.xianyuTemplateIds.length} report=${path.relative(root, reportPath)}`);
