// Read-only product/offer queries. This runtime never opens a billing screen.
'use strict';

var scannerLoader = null;
var scannerClient = null;
var scannerReady = false;
var scannerDisposed = false;
var scannerCounter = 0;

function emit(event) { send(event); }
function useLoader(loader) { Java.classFactory.loader = loader; }
function className(kind) {
  scannerCounter += 1;
  return 'offer.scan.' + kind + Date.now() + '_' + scannerCounter;
}
function errorText(error) { return String(error).slice(0, 1000); }
function nullableString(value) { return value === null ? null : String(value); }

function bootScanner() {
  if (typeof Java === 'undefined') {
    emit({ev: 'scan_error', m: 'Java bridge is unavailable; use the supported Frida 16 client/server.'});
    return;
  }
  var attempts = 0;
  function initialize() {
    if (scannerDisposed) return;
    try {
      useLoader(null);
      var application = Java.use('android.app.ActivityThread').currentApplication();
      if (!application) {
        attempts += 1;
        if (attempts < 25) {
          setTimeout(function () { Java.perform(initialize); }, 200);
          return;
        }
        throw new Error('Google One application context is unavailable.');
      }
      var context = application.getApplicationContext();
      var DexClassLoader = Java.use('dalvik.system.DexClassLoader');
      scannerLoader = DexClassLoader.$new('/data/local/tmp/module_521.apk',
        context.getCodeCacheDir().getAbsolutePath(), null, context.getClassLoader());
      useLoader(scannerLoader);
      var BillingClient = Java.use('com.android.billingclient.api.BillingClient');
      // BillingClient requires this listener even when only querying product details.
      var UpdateListener = Java.registerClass({
        name: className('Updates'),
        implements: [Java.use('com.android.billingclient.api.PurchasesUpdatedListener')],
        methods: {onPurchasesUpdated: function () {}}
      });
      var builder = BillingClient.newBuilder(context);
      builder.setListener(UpdateListener.$new());
      builder.enablePendingPurchases();
      scannerClient = builder.build();
      var StateListener = Java.registerClass({
        name: className('State'),
        implements: [Java.use('com.android.billingclient.api.BillingClientStateListener')],
        methods: {
          onBillingSetupFinished: function (result) {
            if (scannerDisposed) return;
            try {
              var code = Number(result.getResponseCode());
              if (code === 0) {
                scannerReady = true;
                emit({ev: 'ready'});
              } else {
                emit({ev: 'scan_error', code: code, m: String(result.getDebugMessage() || '')});
              }
            } catch (error) {
              emit({ev: 'scan_error', m: errorText(error)});
            }
          },
          onBillingServiceDisconnected: function () {
            scannerReady = false;
            if (!scannerDisposed) emit({ev: 'disconnected'});
          }
        }
      });
      scannerClient.startConnection(StateListener.$new());
    } catch (error) {
      emit({ev: 'scan_error', m: errorText(error)});
    }
  }
  try { Java.perform(initialize); }
  catch (error) { emit({ev: 'scan_error', m: errorText(error)}); }
}

function queryProducts(batchId, products) {
  var finished = false;
  var returnedProducts = [];
  function complete(code, message) {
    if (finished) return;
    finished = true;
    emit({ev: 'query_complete', batch: batchId, code: code,
      msg: message || '', products: returnedProducts, count: returnedProducts.length});
  }
  function fail(error) {
    if (finished) return;
    var message = errorText(error);
    emit({ev: 'query_error', batch: batchId, m: message});
    complete(-1000, message);
  }
  try {
    if (!scannerReady || scannerDisposed) throw new Error('Billing service is not ready.');
    if (!Array.isArray(products) || products.length < 1 || products.length > 20) {
      throw new Error('A batch must contain between 1 and 20 product IDs.');
    }
    products.forEach(function (product) {
      if (typeof product !== 'string' || !/^[a-z0-9][a-z0-9_.-]*$/.test(product)) {
        throw new Error('Invalid product ID: ' + String(product));
      }
    });
    Java.perform(function () {
      try {
        useLoader(scannerLoader);
        var Product = Java.use('com.android.billingclient.api.QueryProductDetailsParams$Product');
        var Params = Java.use('com.android.billingclient.api.QueryProductDetailsParams');
        var ProductDetails = Java.use('com.android.billingclient.api.ProductDetails');
        var OfferDetails = Java.use('com.android.billingclient.api.ProductDetails$SubscriptionOfferDetails');
        var PricingPhase = Java.use('com.android.billingclient.api.ProductDetails$PricingPhase');
        var Listener = Java.registerClass({
          name: className('Query'),
          implements: [Java.use('com.android.billingclient.api.ProductDetailsResponseListener')],
          methods: {
            onProductDetailsResponse: function (result, list) {
              if (finished || scannerDisposed) return;
              var code = -1000;
              var message = '';
              try {
                useLoader(scannerLoader);
                code = Number(result.getResponseCode());
                message = String(result.getDebugMessage() || '');
                if (code !== 0 || !list) return;
                for (var i = 0; i < list.size(); i += 1) {
                  var details = Java.cast(list.get(i), ProductDetails);
                  var id = String(details.getProductId());
                  var title = String(details.getTitle() || '');
                  var name = String(details.getName() || '');
                  returnedProducts.push(id);
                  emit({ev: 'product', batch: batchId, product: id, title: title, name: name});
                  var offers = details.getSubscriptionOfferDetails();
                  if (!offers) continue;
                  for (var j = 0; j < offers.size(); j += 1) {
                    var offer = Java.cast(offers.get(j), OfferDetails);
                    var phaseList = offer.getPricingPhases().getPricingPhaseList();
                    var phases = [];
                    for (var k = 0; k < phaseList.size(); k += 1) {
                      var phase = Java.cast(phaseList.get(k), PricingPhase);
                      phases.push({
                        micros: String(phase.getPriceAmountMicros()),
                        formatted_price: String(phase.getFormattedPrice() || ''),
                        currency: String(phase.getPriceCurrencyCode() || ''),
                        period: String(phase.getBillingPeriod() || ''),
                        cycles: Number(phase.getBillingCycleCount()),
                        recurrence_mode: Number(phase.getRecurrenceMode())
                      });
                    }
                    var tags = [];
                    var tagList = offer.getOfferTags();
                    if (tagList) {
                      for (var t = 0; t < tagList.size(); t += 1) tags.push(String(tagList.get(t)));
                    }
                    emit({ev: 'offer', batch: batchId, product: id,
                      id: nullableString(offer.getOfferId()),
                      base_plan: String(offer.getBasePlanId()),
                      token: String(offer.getOfferToken()), tags: tags,
                      title: title, name: name,
                      micros: phases.length ? phases[0].micros : null,
                      period: phases.length ? phases[0].period : null,
                      phases: phases});
                  }
                }
              } catch (error) {
                code = -1000;
                message = errorText(error);
                emit({ev: 'query_error', batch: batchId, m: message});
              } finally {
                complete(code, message);
              }
            }
          }
        });
        var productList = Java.use('java.util.ArrayList').$new();
        products.forEach(function (id) {
          productList.add(Product.newBuilder().setProductId(id).setProductType('subs').build());
        });
        scannerClient.queryProductDetailsAsync(
          Params.newBuilder().setProductList(productList).build(), Listener.$new());
      } catch (error) { fail(error); }
    });
  } catch (error) { fail(error); }
}

rpc.exports = {
  query: queryProducts,
  dispose: function () {
    scannerDisposed = true;
    scannerReady = false;
    if (typeof Java !== 'undefined' && scannerClient) {
      Java.perform(function () {
        try { useLoader(scannerLoader); scannerClient.endConnection(); }
        catch (_) {}
      });
    }
  }
};

bootScanner();
