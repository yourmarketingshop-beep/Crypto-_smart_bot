import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() => runApp(const CryptoSmartBot());

class CryptoSmartBot extends StatelessWidget {
  const CryptoSmartBot({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Crypto Smart Bot', debugShowCheckedModeBanner: false,
    theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
    home: const Dashboard(),
  );
}

class Dashboard extends StatefulWidget { const Dashboard({super.key}); @override State<Dashboard> createState()=>_DashboardState(); }
class _DashboardState extends State<Dashboard> {
  // Android emulator: 10.0.2.2. For a physical phone, replace with the computer's LAN IP.
  final String baseUrl = const String.fromEnvironment('BOT_API_URL', defaultValue: 'http://10.0.2.2:8000');
  Map<String,dynamic>? account, report, market, signal, backtest, riskEstimate; final entryController=TextEditingController(); final stopController=TextEditingController(); final riskController=TextEditingController(text:'1'); List<dynamic> positions=[]; String selectedSymbol='BTCUSDT'; String status='اضغط تحديث لجلب بيانات الخادم'; bool loading=false;
  Future<void> loadSignal() async {
    try { final r=await http.get(Uri.parse('$baseUrl/market/signal/$selectedSymbol')); if(r.statusCode!=200) throw Exception('HTTP ${r.statusCode}'); if(mounted) setState(()=>signal=jsonDecode(r.body)); } catch(e) { if(mounted) setState(()=>signal={'error':'تعذر حساب الإشارة: $e'}); }
  }
  Future<void> runBacktest() async {
    if(mounted) setState(()=>loading=true);
    try { final r=await http.get(Uri.parse('$baseUrl/paper/backtest/$selectedSymbol?limit=500')); if(r.statusCode!=200) throw Exception('HTTP ${r.statusCode}: ${r.body}'); if(mounted) setState(()=>backtest=jsonDecode(r.body)); } catch(e) { if(mounted) setState(()=>backtest={'error':'تعذر الاختبار التاريخي: $e'}); } finally { if(mounted) setState(()=>loading=false); }
  }
  Future<void> calculateRisk() async {
    try {
      final r=await http.post(Uri.parse('$baseUrl/paper/risk/size'),headers:{'Content-Type':'application/json'},body:jsonEncode({'symbol':selectedSymbol,'entry_price':double.parse(entryController.text),'stop_loss':double.parse(stopController.text),'risk_percent':double.parse(riskController.text)}));
      if(r.statusCode!=200) throw Exception('HTTP ${r.statusCode}: ${r.body}');
      if(mounted) setState(()=>riskEstimate=jsonDecode(r.body));
    } catch(e) { if(mounted) setState(()=>riskEstimate={'error':'تعذر حساب حجم المركز: $e'}); }
  }
  Future<void> loadIndicators() async {
    try {
      final r=await http.get(Uri.parse('$baseUrl/market/indicators/$selectedSymbol'));
      if(r.statusCode!=200) throw Exception('HTTP ${r.statusCode}: ${r.body}');
      if(mounted) setState(()=>market=jsonDecode(r.body)); await loadSignal();
    } catch(e) { if(mounted) setState(()=>market={'error':'تعذر جلب المؤشرات: $e'}); }
  }
  Future<void> refresh() async {
    setState(()=>loading=true);
    try {
      final responses=await Future.wait([http.get(Uri.parse('$baseUrl/paper/account')),http.get(Uri.parse('$baseUrl/paper/positions')),http.get(Uri.parse('$baseUrl/paper/report'))]);
      if(responses.any((r)=>r.statusCode!=200)) throw Exception('HTTP ${responses.map((e)=>e.statusCode).join(', ')}');
      setState(() { account=jsonDecode(responses[0].body); positions=jsonDecode(responses[1].body); report=jsonDecode(responses[2].body); status='متصل – تداول افتراضي فقط'; });
      await loadIndicators();
    } catch(e) { setState(()=>status='تعذر الاتصال: $e'); } finally { setState(()=>loading=false); }
  }
  @override Widget build(BuildContext context)=>Scaffold(
    appBar: AppBar(title: const Text('Crypto Smart Bot'), actions:[IconButton(onPressed:loading?null:refresh,icon:const Icon(Icons.refresh))]),
    body: RefreshIndicator(onRefresh:refresh,child:ListView(padding:const EdgeInsets.all(16),children:[
      Card(child:Padding(padding:const EdgeInsets.all(16),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[const Text('حالة النظام'),const SizedBox(height:8),Text(status),const SizedBox(height:8),const Chip(label:Text('PAPER TRADING ONLY – أموال افتراضية'))]))),
      if(loading) const LinearProgressIndicator(),
      Card(child:ListTile(title:const Text('الرصيد النقدي الافتراضي'),subtitle:Text(account==null?'—':'${(account!['cash'] as num).toStringAsFixed(2)} USDT'))),
      Card(child:ListTile(title:const Text('عدد الصفقات'),subtitle:Text(report==null?'—':'${report!['trade_count']}'))),
      Card(child:Padding(padding:const EdgeInsets.all(16),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        const Text('تحليل السوق والمؤشرات الفنية',style:TextStyle(fontSize:18,fontWeight:FontWeight.bold)),
        const SizedBox(height:10),
        DropdownButton<String>(value:selectedSymbol,isExpanded:true,items:const [DropdownMenuItem(value:'BTCUSDT',child:Text('Bitcoin – BTC/USDT')),DropdownMenuItem(value:'ETHUSDT',child:Text('Ethereum – ETH/USDT')),DropdownMenuItem(value:'SOLUSDT',child:Text('Solana – SOL/USDT'))],onChanged:loading?null:(v){if(v!=null){setState(() { selectedSymbol=v; signal=null; backtest=null; });loadIndicators();}}),
        if(market==null) const Text('اضغط تحديث لتحميل المؤشرات.'),
        if(market?['error']!=null) Text('${market!['error']}'),
        if(signal?['error']!=null) Text('${signal!['error']}'),
        if(signal?['signal']!=null) Card(child:ListTile(title:Text('الإشارة التحليلية: ${signal!['signal']}'),subtitle:Text('توافق الشروط: ${signal!['score']}% – ${signal!['score_label']}'))),
        if(market?['indicators']!=null) ...[
          Text('السعر: ${(market!['price'] as num).toStringAsFixed(4)} USDT'),
          Text('RSI (14): ${market!['indicators']['rsi_14']}'),
          Text('EMA 12: ${market!['indicators']['ema_12']}'),
          Text('EMA 26: ${market!['indicators']['ema_26']}'),
          Text('EMA 50: ${market!['indicators']['ema_50']??'بيانات غير كافية'}'),
          Text('MACD: ${market!['indicators']['macd']}'),
          Text('إشارة MACD: ${market!['indicators']['macd_signal']}'),
          Text('Histogram: ${market!['indicators']['macd_histogram']}'),
          const SizedBox(height:6),
          FilledButton.tonalIcon(onPressed:loading?null:runBacktest,icon:const Icon(Icons.science),label:const Text('تشغيل اختبار تاريخي افتراضي')),
          if(backtest?['error']!=null) Text('${backtest!['error']}'),
          if(backtest?['final_equity']!=null) Text('نتيجة الاختبار: ${backtest!['final_equity']} USDT | الربح/الخسارة: ${backtest!['net_profit']} USDT | الصفقات المغلقة: ${backtest!['closed_trades']}'),
          const Text('الاختبار يفترض رسوماً 0.1% لكل جانب، ولا يشمل الانزلاق السعري.'),
          const Text('المصدر: Binance العام | إطار دقيقة واحدة | آخر شمعة غير مكتملة مستبعدة',style:TextStyle(fontSize:11)),
        ],
      ]))),
      Card(child:Padding(padding:const EdgeInsets.all(16),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        const Text('حاسبة حجم المركز وإدارة المخاطر',style:TextStyle(fontSize:18,fontWeight:FontWeight.bold)),
        const Text('أدخل سعر الدخول ووقف الخسارة ونسبة المخاطرة. الحد الأقصى 2% من النقد المتاح.'),
        TextField(controller:entryController,keyboardType:const TextInputType.numberWithOptions(decimal:true),decoration:const InputDecoration(labelText:'سعر الدخول (USDT)')),
        TextField(controller:stopController,keyboardType:const TextInputType.numberWithOptions(decimal:true),decoration:const InputDecoration(labelText:'وقف الخسارة (USDT)')),
        TextField(controller:riskController,keyboardType:const TextInputType.numberWithOptions(decimal:true),decoration:const InputDecoration(labelText:'نسبة المخاطرة % (حتى 2)')),
        const SizedBox(height:8),FilledButton.tonalIcon(onPressed:loading?null:calculateRisk,icon:const Icon(Icons.calculate),label:const Text('احسب حجم المركز')),
        if(riskEstimate?['error']!=null) Text('${riskEstimate!['error']}'),
        if(riskEstimate?['quantity']!=null) Text('الكمية التقديرية: ${riskEstimate!['quantity']} | قيمة المركز: ${riskEstimate!['notional']} USDT\nالخسارة المقدرة عند الوقف: ${riskEstimate!['estimated_loss_at_stop']} USDT | رسوم الدخول: ${riskEstimate!['estimated_entry_fee']} USDT\n${riskEstimate!['note']}'),
      ]))),
      const Padding(padding:EdgeInsets.symmetric(vertical:12),child:Text('المراكز المفتوحة',style:TextStyle(fontSize:18,fontWeight:FontWeight.bold))),
      if(positions.isEmpty) const Text('لا توجد مراكز مفتوحة أو لم يتم تحميل البيانات.'),
      ...positions.map((p)=>Card(child:ListTile(title:Text('${p['symbol']}'),subtitle:Text('الكمية: ${p['quantity']}  |  متوسط الدخول: ${p['avg_price']}\nوقف الخسارة: ${p['stop_loss']??'غير محدد'}  |  جني الأرباح: ${p['take_profit']??'غير محدد'}')))),
      const SizedBox(height:12), FilledButton.icon(onPressed:loading?null:refresh,icon:const Icon(Icons.sync),label:const Text('تحديث البيانات')),
      const Text('المؤشرات لأغراض التحليل فقط وليست ضماناً للربح أو توصية آلية. عمليات الشراء والبيع محاكاة بأموال افتراضية فقط؛ لا توجد أوامر تداول حقيقية.'),
    ])),
  );
}
