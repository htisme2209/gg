// Subscription ownership diagnostics only. No checkout or transaction APIs.
'use strict';

var purchaseDiagnosticClient = null;
var purchaseDiagnosticLoader = null;
var purchaseDiagnosticDone = false;
var purchaseDiagnosticDisposed = false;
var purchaseDiagnosticQueried = false;
var purchaseDiagnosticCounter = 0;

function diagnosticLoader(loader) { Java.classFactory.loader = loader; }
function diagnosticClass(kind) {
  purchaseDiagnosticCounter += 1;
  return 'purchase.diagnostic.' + kind + Date.now() + '_' + purchaseDiagnosticCounter;
}
function diagnosticError(stage, code) {
  if (purchaseDiagnosticDone || purchaseDiagnosticDisposed) return;
  purchaseDiagnosticDone = true;
  send({ev: 'purchases_error', stage: stage,
    code: Number.isInteger(code) ? code : -1000});
}

function queryOwnedSubscriptions() {
  if (purchaseDiagnosticQueried || purchaseDiagnosticDone || purchaseDiagnosticDisposed) return;
  purchaseDiagnosticQueried = true;
  try {
    diagnosticLoader(purchaseDiagnosticLoader);
    var Params = Java.use('com.android.billingclient.api.QueryPurchasesParams');
    var Purchase = Java.use('com.android.billingclient.api.Purchase');
    var Listener = Java.registerClass({
      name: diagnosticClass('Query'),
      implements: [Java.use('com.android.billingclient.api.PurchasesResponseListener')],
      methods: {
        onQueryPurchasesResponse: function (result, list) {
          if (purchaseDiagnosticDone || purchaseDiagnosticDisposed) return;
          var code;
          try {
            code = Number(result.getResponseCode());
            if (!Number.isInteger(code)) throw new Error('Invalid response code');
          } catch (_) {
            diagnosticError('response', -1000);
            return;
          }
          if (code !== 0) {
            diagnosticError('response', code);
            return;
          }
          if (list === null || list === undefined) {
            diagnosticError('response', -1000);
            return;
          }
          var purchases = [];
          try {
            diagnosticLoader(purchaseDiagnosticLoader);
            for (var i = 0; i < list.size(); i += 1) {
              var purchase = Java.cast(list.get(i), Purchase);
              var productList = purchase.getProducts();
              if (productList === null || productList === undefined) {
                throw new Error('Missing product list');
              }
              var products = [];
              for (var j = 0; j < productList.size(); j += 1) {
                var id = String(productList.get(j));
                if (id.length <= 200 && /^g1\.[a-z0-9_]+(?:[.\-][a-z0-9_]+)*$/.test(id)
                    && products.indexOf(id) === -1) products.push(id);
              }
              var state = Number(purchase.getPurchaseState());
              if (!Number.isInteger(state)) throw new Error('Invalid purchase state');
              // Read the token only to derive presence. Its value never leaves this runtime.
              var token = purchase.getPurchaseToken();
              var tokenPresent = token !== null && token !== undefined && String(token).trim().length > 0;
              purchases.push({products: products, purchase_state: state,
                auto_renewing: !!purchase.isAutoRenewing(),
                acknowledged: !!purchase.isAcknowledged(), token_present: tokenPresent});
            }
          } catch (_) {
            diagnosticError('purchase_parse', -1000);
            return;
          }
          if (purchaseDiagnosticDone || purchaseDiagnosticDisposed) return;
          purchaseDiagnosticDone = true;
          send({ev: 'purchases_complete', code: 0, purchases: purchases});
        }
      }
    });
    var params = Params.newBuilder().setProductType('subs').build();
    purchaseDiagnosticClient.queryPurchasesAsync(params, Listener.$new());
  } catch (_) {
    diagnosticError('query', -1000);
  }
}

function bootPurchaseDiagnostic() {
  if (typeof Java === 'undefined') {
    diagnosticError('java_bridge', -1000);
    return;
  }
  var attempts = 0;
  function initialize() {
    if (purchaseDiagnosticDone || purchaseDiagnosticDisposed) return;
    var stage = 'application';
    try {
      diagnosticLoader(null);
      var application = Java.use('android.app.ActivityThread').currentApplication();
      if (!application) {
        attempts += 1;
        if (attempts < 25) {
          setTimeout(function () {
            try { Java.perform(initialize); }
            catch (_) { diagnosticError('initialization', -1000); }
          }, 200);
          return;
        }
        diagnosticError('application', -1000);
        return;
      }
      var context = application.getApplicationContext();
      stage = 'module';
      purchaseDiagnosticLoader = Java.use('dalvik.system.DexClassLoader').$new(
        '/data/local/tmp/module_521.apk', context.getCodeCacheDir().getAbsolutePath(),
        null, context.getClassLoader());
      diagnosticLoader(purchaseDiagnosticLoader);
      stage = 'client';
      var Client = Java.use('com.android.billingclient.api.BillingClient');
      // Required by BillingClient.newBuilder, but does not initiate any purchase.
      var Updates = Java.registerClass({
        name: diagnosticClass('Updates'),
        implements: [Java.use('com.android.billingclient.api.PurchasesUpdatedListener')],
        methods: {onPurchasesUpdated: function () {}}
      });
      var builder = Client.newBuilder(context);
      builder.setListener(Updates.$new());
      builder.enablePendingPurchases();
      purchaseDiagnosticClient = builder.build();
      var State = Java.registerClass({
        name: diagnosticClass('State'),
        implements: [Java.use('com.android.billingclient.api.BillingClientStateListener')],
        methods: {
          onBillingSetupFinished: function (result) {
            if (purchaseDiagnosticDone || purchaseDiagnosticDisposed) return;
            try {
              var code = Number(result.getResponseCode());
              if (!Number.isInteger(code)) throw new Error('Invalid setup code');
              if (code !== 0) diagnosticError('setup', code);
              else queryOwnedSubscriptions();
            } catch (_) { diagnosticError('setup', -1000); }
          },
          onBillingServiceDisconnected: function () {
            diagnosticError('disconnected', -1);
          }
        }
      });
      purchaseDiagnosticClient.startConnection(State.$new());
    } catch (_) {
      diagnosticError(stage, -1000);
    }
  }
  try { Java.perform(initialize); }
  catch (_) { diagnosticError('initialization', -1000); }
}

rpc.exports = {
  dispose: function () {
    purchaseDiagnosticDisposed = true;
    if (typeof Java === 'undefined' || !purchaseDiagnosticClient) return;
    try {
      Java.perform(function () {
        try {
          diagnosticLoader(purchaseDiagnosticLoader);
          purchaseDiagnosticClient.endConnection();
        } catch (_) {}
      });
    } catch (_) {}
  }
};

bootPurchaseDiagnostic();
