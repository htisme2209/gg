'use strict';

// Run with: node test_purchase_scan.js
// All Java/Billing calls are mocks; this never contacts a device.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, 'purchase_scan.js'), 'utf8');
new vm.Script(source);

function list(items) {
  return {size: () => items.length, get: (index) => items[index]};
}

function result(code = 0) {
  return {
    getResponseCode: () => code,
    getDebugMessage: () => { throw new Error('RAW-DEBUG-SECRET'); }
  };
}

function purchase(options = {}) {
  return {
    getProducts: () => options.products === null ? null : list(
      options.products === undefined ? ['g1.2tb.ai.subs_variant'] : options.products),
    getPurchaseState: () => options.state === undefined ? 1 : options.state,
    getPurchaseToken: () => options.token === undefined ? 'RAW-TOKEN-SECRET' : options.token,
    isAutoRenewing: () => !!options.renewing,
    isAcknowledged: () => options.acknowledged === undefined ? true : options.acknowledged,
    getOriginalJson: () => { throw new Error('RAW-RECEIPT-SECRET'); },
    getOrderId: () => { throw new Error('RAW-ORDER-SECRET'); }
  };
}

function harness(options = {}) {
  const messages = [];
  const state = {queryCalls: 0, endCalls: 0, setup: null, response: null};
  const client = {
    startConnection(listener) {
      state.setup = listener;
      if (!options.deferSetup) {
        listener.onBillingSetupFinished(result(options.setupCode || 0));
        if (options.doubleSetup) listener.onBillingSetupFinished(result(0));
      }
    },
    queryPurchasesAsync(params, listener) {
      state.queryCalls += 1;
      state.params = params;
      state.response = listener;
      if (options.queryThrow) throw new Error('RAW-QUERY-SECRET');
      if (!options.deferResponse) {
        const response = options.nullList ? null : list(options.purchases || []);
        listener.onQueryPurchasesResponse(result(options.responseCode || 0), response);
        if (options.doubleResponse) listener.onQueryPurchasesResponse(result(0), response);
      }
    },
    endConnection() { state.endCalls += 1; }
  };
  const builder = {
    setListener() { return this; },
    enablePendingPurchases() { return this; },
    build: () => client
  };
  const java = {
    classFactory: {loader: null},
    perform: (callback) => callback(),
    cast: (value) => value,
    registerClass: (specification) => ({$new: () => specification.methods}),
    use(name) {
      if (name === 'android.app.ActivityThread') {
        return {currentApplication: () => ({getApplicationContext: () => ({
          getCodeCacheDir: () => ({getAbsolutePath: () => '/mock/cache'}),
          getClassLoader: () => ({})
        })})};
      }
      if (name === 'dalvik.system.DexClassLoader') return {$new: () => ({})};
      if (name === 'com.android.billingclient.api.BillingClient') {
        return {newBuilder: () => builder};
      }
      if (name === 'com.android.billingclient.api.QueryPurchasesParams') {
        return {newBuilder: () => ({
          setProductType(type) { this.type = type; return this; },
          build() { return {type: this.type}; }
        })};
      }
      if (/BillingFlowParams|ProductDetails|SubscriptionUpdate/.test(name)) {
        throw new Error('Forbidden transaction/product-query class requested');
      }
      return {name};
    }
  };
  const context = vm.createContext({
    Java: java,
    rpc: {exports: {}},
    send: (message) => messages.push(JSON.parse(JSON.stringify(message))),
    setTimeout: (callback) => callback()
  });
  new vm.Script(source).runInContext(context);
  return {messages, state, context, exports: context.rpc.exports};
}

const passed = [];
function test(name, callback) {
  callback();
  passed.push(name);
}

test('nonrenewing owned entry exposes metadata and token boolean only', () => {
  const h = harness({purchases: [purchase({
    renewing: false,
    products: ['g1.2tb.ai.subs_variant', 'secret@example.com', 'g1.bad@secret', 'g1.play.20tb']
  })]});
  assert.deepEqual(h.messages, [{ev: 'purchases_complete', code: 0, purchases: [{
    products: ['g1.2tb.ai.subs_variant', 'g1.play.20tb'], purchase_state: 1,
    auto_renewing: false, acknowledged: true, token_present: true
  }]}]);
  assert.equal(h.state.params.type, 'subs');
  assert.equal(JSON.stringify(h.messages).includes('SECRET'), false);
});

test('an actual empty list succeeds', () => {
  assert.deepEqual(harness().messages, [{ev: 'purchases_complete', code: 0, purchases: []}]);
});

test('a null purchase list is a response error, not zero owned entries', () => {
  assert.deepEqual(harness({nullList: true}).messages,
    [{ev: 'purchases_error', stage: 'response', code: -1000}]);
});

test('a null product list is a parsing error, not an empty product collection', () => {
  assert.deepEqual(harness({purchases: [purchase({products: null})]}).messages,
    [{ev: 'purchases_error', stage: 'purchase_parse', code: -1000}]);
});

test('Billing errors expose fixed stage and code only', () => {
  assert.deepEqual(harness({responseCode: 6}).messages,
    [{ev: 'purchases_error', stage: 'response', code: 6}]);
});

test('parsing exceptions do not leak receipt, token, or email values', () => {
  const broken = purchase();
  broken.getProducts = () => { throw new Error('RAW-TOKEN-SECRET secret@example.com'); };
  const h = harness({purchases: [broken]});
  assert.deepEqual(h.messages, [{ev: 'purchases_error', stage: 'purchase_parse', code: -1000}]);
  assert.equal(JSON.stringify(h.messages).includes('SECRET'), false);
  assert.equal(JSON.stringify(h.messages).includes('@'), false);
});

test('duplicate setup/response callbacks query and emit only once', () => {
  const h = harness({doubleSetup: true, doubleResponse: true, purchases: [purchase()]});
  assert.equal(h.state.queryCalls, 1);
  assert.equal(h.messages.length, 1);
});

test('dispose ends the connection and suppresses late results', () => {
  const h = harness({deferResponse: true});
  h.exports.dispose();
  h.state.response.onQueryPurchasesResponse(result(0), list([purchase()]));
  assert.equal(h.messages.length, 0);
  assert.equal(h.state.endCalls, 1);
});

test('setup and invocation errors never emit raw exception text', () => {
  const setup = harness({setupCode: 3});
  assert.deepEqual(setup.messages, [{ev: 'purchases_error', stage: 'setup', code: 3}]);
  assert.equal(setup.state.queryCalls, 0);
  assert.deepEqual(harness({queryThrow: true}).messages,
    [{ev: 'purchases_error', stage: 'query', code: -1000}]);
});

console.log(JSON.stringify({syntax: 'OK', passed: passed.length, checks: passed}, null, 2));
