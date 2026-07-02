import assert from 'node:assert/strict';
import test from 'node:test';

import { compactReadSelectors, minimalActionForPhone } from '../lib/vision-safety.mjs';

test('minimalActionForPhone normalizes waitElement and preserves resourceId', () => {
  const body = minimalActionForPhone({
    action: 'waitElement',
    resourceId: 'com.example:id/done',
    timeoutMs: 1800,
  });

  assert.equal(body.action, 'wait_element');
  assert.equal(body.resourceId, 'com.example:id/done');
  assert.equal(body.timeoutMs, 1800);
});

test('compactReadSelectors preserves direct action bodies from observe_fast', () => {
  const selectors = compactReadSelectors([
    {
      nodeId: 'node-1',
      label: 'Search',
      actionBody: {
        action: 'clickDescription',
        contentDescription: 'Search',
      },
    },
    {
      nodeId: 'node-2',
      label: 'Done',
      actionBody: {
        action: 'click_element',
        resourceId: 'com.example:id/done',
      },
    },
  ]);

  assert.equal(selectors.length, 2);
  assert.equal(selectors[0].actionBody.action, 'click_description');
  assert.equal(selectors[0].actionBody.contentDescription, 'Search');
  assert.equal(selectors[1].actionBody.action, 'click_element');
  assert.equal(selectors[1].actionBody.resourceId, 'com.example:id/done');
});
