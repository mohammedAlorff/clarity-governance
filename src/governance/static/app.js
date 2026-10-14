'use strict';

const views = { overview: 'Overview', schema: 'Schema explorer', review: 'Review queue', dictionary: 'Data dictionary', quality: 'Quality report', evaluation: 'Evaluation', privacy: 'Privacy' };
const app = { state: null, view: 'overview', busy: false, filter: 'pending', search: '', dictionary: null, dictionaryLoading: false, dialog: null };
app.inspectionMode = 'agent';
app.limits = { max_calls: 40, max_steps: 8, max_seconds: 60, max_tokens: 16000, max_output_tokens: 3000, max_retries: 1 };
app.preflight = null;
const main = document.getElementById('main');
const dialog = document.getElementById('proposal-dialog');
const uiTranslations = {
  'Overview':'نظرة عامة','Schema explorer':'مستكشف المخطط','Review queue':'قائمة المراجعة',
  'Data dictionary':'قاموس البيانات','Quality report':'تقرير الجودة','Evaluation':'التقييم','Privacy':'الخصوصية',
  'Workspace':'مساحة العمل','Synthetic demo · local':'عرض اصطناعي · محلي','Source disconnected':'المصدر غير متصل',
  'Checking model…':'جارٍ التحقق من إعداد النموذج…','Check model configuration':'تحقق من إعداد النموذج',
  'Local model configured · availability not tested':'النموذج المحلي مضبوط · لم يتم التحقق من توفره',
  'Connect a data source':'اربط مصدر البيانات','Inspect and propose':'افحص واقترح',
  'Inspect schema and bounded metrics to propose descriptions and quality rules.':'افحص المخطط ومؤشرات الجودة لاقتراح أوصاف وقواعد حوكمة.',
  'Connect source':'اربط المصدر','MySQL · server environment':'MySQL · إعدادات الخادم',
  'Synthetic demo':'عرض اصطناعي','Deterministic demo':'عرض توضيحي ثابت',
  'Adaptive agent · model required':'الوكيل التكيفي · يتطلب نموذجًا','Fixed workflow · model required':'مسار ثابت · يتطلب نموذجًا',
  'Check readiness':'تحقق من الجاهزية','Start inspection':'ابدأ الفحص','Inspect':'افحص',
  'Run approved checks':'شغّل القواعد المعتمدة','Your next steps':'خطواتك التالية',
  'Human review at every decision':'مراجعة بشرية لكل قرار','Awaiting your review':'بانتظار مراجعتك',
  'Inspection activity':'نشاط الفحص','Tables in scope':'الجداول في النطاق','Columns discovered':'الأعمدة المكتشفة',
  'Awaiting review':'بانتظار المراجعة','Quality score':'مؤشر الجودة',
  'From the connected schema':'من مخطط المصدر المتصل','Ready for documentation':'جاهز للتوثيق',
  'Decisions need your attention':'قرارات تحتاج مراجعتك','Run approved checks to measure':'شغّل القواعد المعتمدة لقياس الجودة',
  'GOVERNANCE PIPELINE':'مسار حوكمة البيانات','Schema profiler':'مستكشف المخطط','SQL quality':'جودة SQL',
  'Privacy guard':'حماية الخصوصية','Governance agent':'وكيل الحوكمة','Steward store':'سجل القرارات',
  'RUNTIME STATUS':'حالة التشغيل','Read only · Model values filtered':'قراءة فقط · تُحجب القيم عن النموذج',
  'Local workspace':'مساحة محلية','Governance with evidence':'حوكمة مدعومة بالأدلة',
  'Read only · Human reviewed':'قراءة فقط · القرارات بمراجعة بشرية',
  'Approve':'اعتماد','Edit proposal':'عدّل المقترح','Clarify':'طلب توضيح','Reject':'رفض',
  'All proposals':'كل المقترحات','Approved':'معتمد','Reviewer':'المراجع','Your name':'اسم المراجع',
  'Local checks passed':'اجتازت الفحوصات المحلية','Configuration present · provider not tested':'الإعداد موجود · لم يتم اختبار المزوّد','Not ready to start':'غير جاهز للبدء',
  'Inspection audit':'سجل الفحص','Schema in this scope':'المخطط في هذا النطاق',
  'Tool calls':'استدعاءات الأدوات','Model requests':'طلبات النموذج','Input tokens':'رموز الإدخال',
  'Output tokens':'رموز الإخراج','Total tokens':'إجمالي الرموز','Elapsed seconds':'مدة التنفيذ بالثواني',
  'Unknown':'غير معروف','Not recorded':'غير مسجل','No schema loaded':'لم يُحمّل أي مخطط',
  'Check definition and population':'تعريف الفحص ونطاقه','Executable rule configuration':'إعداد قاعدة التنفيذ',
  'Your Governance Workspace':'مساحة حوكمة البيانات','Quality report':'تقرير الجودة'
};
Object.assign(uiTranslations, {
  'YOUR GOVERNANCE WORKSPACE':'مساحة حوكمة البيانات',
  'A clearer picture of your data.':'صورة أوضح لبياناتك.',
  'From schema to shared understanding. Inspect your source, review the evidence, and turn decisions into measurable quality.':'من المخطط إلى فهم مشترك. افحص مصدرك، راجع الأدلة، وحوّل القرارات إلى جودة قابلة للقياس.',
  'Review proposals':'راجع المقترحات',
  'YOUR LOCAL WORKSPACE':'مساحة العمل المحلية',
  'Bring your source into focus.':'استكشف مصدرك بوضوح.',
  'Source data is read-only. Review proposals before explicitly running approved checks against this inspection scope.':'بيانات المصدر للقراءة فقط. راجع المقترحات قبل تشغيل القواعد المعتمدة على نطاق الفحص.',
  'Use the configured, read-only MySQL source. Model processing begins only when you start an inspection.':'استخدم مصدر MySQL مضبوطًا للقراءة فقط. لا يبدأ النموذج العمل إلا عند بدء الفحص.',
  'Your next steps':'خطواتك التالية',
  'Human review at every decision':'مراجعة بشرية عند كل قرار',
  'Inspection limits':'حدود الفحص',
  'Review the evidence':'راجع الأدلة',
  'Approve, edit, reject, or request clarification. Every edit creates a new draft version.':'اعتمد المقترح أو عدّله أو ارفضه أو اطلب توضيحًا. كل تعديل ينشئ مسودة جديدة.',
  'Open review queue':'افتح قائمة المراجعة',
  'Approval does not execute checks. Run the current approved rules when you are ready.':'الاعتماد لا يشغّل الفحوصات. شغّل القواعد المعتمدة عندما تكون مستعدًا.',
  'A clean slate.':'لا توجد مقترحات بعد.',
  'Start an inspection to surface proposals for review.':'ابدأ الفحص لإنشاء مقترحات لمراجعتها.',
  'View review queue':'اعرض قائمة المراجعة',
  'Inspection activity':'نشاط الفحص',
  'Inspection runs will appear here. No inspection has been recorded for this scope.':'ستظهر عمليات الفحص هنا. لم يُسجّل فحص لهذا النطاق.',
  'Connect a data source':'اربط مصدر البيانات',
  'Synthetic records are ready for a complete local walkthrough.':'البيانات الاصطناعية جاهزة لاستعراض محلي كامل.',
  'MySQL · server environment':'MySQL · إعدادات الخادم',
  'Source':'المصدر','Model':'النموذج','Demo':'عرض توضيحي','Disconnected':'غير متصل',
  'Run approved checks':'شغّل القواعد المعتمدة','Start inspection':'ابدأ الفحص',
  'No source selected':'لم يُحدّد مصدر','No source connected':'لا يوجد مصدر متصل',
  '0 pending':'0 بانتظار المراجعة','0 recorded':'لا توجد عمليات مسجلة',
  'Synthetic demo workspace':'مساحة العرض الاصطناعي',
  'Connected data workspace':'مساحة البيانات المتصلة',
  'CONNECTED DATA WORKSPACE':'مساحة بيانات متصلة',
  'SYNTHETIC DEMO WORKSPACE':'مساحة عرض اصطناعي',
  'Your local workspace':'مساحة العمل المحلية',
  'Local · configured':'محلي · الإعداد موجود',
  'Source connected. A fresh inspection scope is ready.':'تم الاتصال بالمصدر. نطاق فحص جديد جاهز.',
  'Could not connect. Check the server environment, selected MySQL schema, read-only grants, and connection settings.':'تعذر الاتصال. تحقق من إعدادات الخادم ومخطط MySQL وصلاحيات القراءة فقط.',
  'Source connected':'المصدر متصل',
  'MySQL connected':'MySQL متصل',
  'Local configuration check only. Credentials, model access, source freshness, and sufficient time or tokens are not verified. No provider request was sent.':'هذا فحص للإعداد المحلي فقط. لم يتم التحقق من بيانات الاعتماد أو توفر النموذج أو حداثة المصدر أو كفاية الوقت والرموز. لم يُرسل أي طلب إلى المزوّد.',
  'KNOW YOUR SOURCE':'اكتشف مصدرك',
  'EVIDENCE BEFORE ACTION':'الأدلة قبل الإجراء',
  'A SHARED LANGUAGE':'لغة مشتركة',
  'A living reference for your schema, with proposed and approved descriptions clearly identified.':'مرجع حيّ لمخططك، يميّز بوضوح بين الأوصاف المقترحة والمعتمدة.',
  'source descriptions and review status':'أوصاف المصدر وحالة المراجعة',
  'MEASURE WHAT MATTERS':'قِس ما يهم',
  'VALIDATE WITH REAL EVIDENCE':'تحقق بأدلة فعلية',
  'CONTROL WHAT LEAVES YOUR SOURCE':'تحكم فيما يغادر مصدرك',
  'Data governance pipeline':'مسار حوكمة البيانات',
  'Data source':'مصدر البيانات',
  'Clarity overview':'نظرة عامة على Clarity',
  'Explore the structure behind your data. Tables, types, and declared relationships come directly from the connected source.':'استكشف بنية بياناتك. تأتي الجداول والأنواع والعلاقات المعلنة مباشرة من المصدر المتصل.',
  'Inspect source':'افحص المصدر',
  'Search schema':'ابحث في المخطط',
  'Search tables and columns…':'ابحث عن الجداول والأعمدة…',
  'COLUMN':'العمود','DATA TYPE':'نوع البيانات','NULLABLE':'يقبل قيمة فارغة','KEY':'المفتاح',
  'Yes':'نعم','No':'لا','Nullable':'يقبل قيمة فارغة','Not nullable':'لا يقبل قيمة فارغة',
  'Declared relationships':'العلاقات المعلنة','Source metadata':'بيانات المصدر',
  'No declared relationships were returned by this schema.':'لم يُرجع هذا المخطط علاقات معلنة.',
  'Tables':'الجداول','Columns':'الأعمدة','rows':'صفوف','columns':'أعمدة','tables':'جداول',
  'Every proposal is a starting point. Review the evidence and assumptions, then decide what belongs in your governance standard.':'كل مقترح نقطة بداية. راجع الأدلة والافتراضات ثم قرر ما يناسب معيار الحوكمة لديك.',
  'Awaiting review':'بانتظار المراجعة','All proposals':'كل المقترحات','Approved':'معتمد','Reviewer':'المراجع',
  'Approving a rule records your decision. Checks run only when you select “Run approved checks.”':'اعتماد القاعدة يسجل قرارك. لا تعمل الفحوصات إلا عند اختيار «شغّل القواعد المعتمدة».',
  'Search the dictionary…':'ابحث في القاموس…','Table / column':'الجدول / العمود','Type':'النوع',
  'Description':'الوصف','Review status':'حالة المراجعة','Version':'الإصدار',
  'Export CSV':'تصدير CSV','Search dictionary':'ابحث في القاموس',
  'No reviewed description yet':'لا يوجد وصف تمت مراجعته بعد','Not documented':'غير موثق',
  'Draft':'مسودة','Needs clarification':'يحتاج إلى توضيح','Rejected':'مرفوض',
  'Not applicable':'لا ينطبق','No eligible data':'لا توجد بيانات مؤهلة','Not run':'لم يُشغّل',
  'Failed':'فشل','Budget exhausted':'انتهت الميزانية','Provider unavailable':'المزوّد غير متاح',
  'Partial':'جزئي',
  'Quality at a glance':'نظرة سريعة على الجودة','Check results':'نتائج الفحوصات',
  'Check coverage':'تغطية الفحوصات','Completed':'مكتمل','applicable':'ينطبق','Generated':'تاريخ الإنشاء',
  'Profiled columns':'الأعمدة المفحوصة','overall quality':'الجودة الإجمالية',
  'Completeness':'الاكتمال','Uniqueness':'التفرّد','Validity':'الصلاحية','Consistency':'الاتساق',
  'Synthetic demonstration':'عرض اصطناعي','Provider trials':'تجارب المزوّد','Human reference review':'مراجعة بشرية مرجعية',
  'What the model can see':'ما يمكن للنموذج رؤيته','Sampling and limits':'العينات والحدود',
  'Outbound privacy audit':'سجل الخصوصية للإرسال','Review proposal':'راجع المقترح','Save review':'احفظ المراجعة',
  'PROPOSAL REVIEW':'مراجعة المقترح','Reviewer name':'اسم المراجع','Review note':'ملاحظة المراجعة',
  'Edit proposal · create a new draft':'تعديل المقترح · إنشاء مسودة جديدة',
  'Save new draft':'احفظ المسودة الجديدة','Request clarification':'اطلب توضيحًا',
  'Approve proposal':'اعتمد المقترح','Reject proposal':'ارفض المقترح','Clarify proposal':'اطلب توضيح المقترح',
  'Title':'العنوان','Evidence':'الأدلة','Assumptions':'الافتراضات','Clarification request':'طلب التوضيح',
  'Executable rule · JSON':'قاعدة قابلة للتنفيذ · JSON','Cancel':'إلغاء','Close dialog':'إغلاق النافذة',
  'One item per line. Preserve the evidence used to reach this decision.':'عنصر واحد في كل سطر. احتفظ بالأدلة التي استند إليها هذا القرار.',
  'One assumption per line.':'افتراض واحد في كل سطر.',
  'Use metric_id, target, and parameters. The server validates the configuration before saving.':'استخدم metric_id وtarget وparameters. يتحقق الخادم من الإعداد قبل الحفظ.',
  'Approval records the decision. It does not run checks.':'الاعتماد يسجل القرار ولا يشغّل الفحوصات.',
  'The current version is preserved. Your edit creates a new draft requiring approval.':'يُحفظ الإصدار الحالي. ينشئ تعديلك مسودة جديدة تتطلب الاعتماد.',
  'Your note becomes part of the review history.':'تصبح ملاحظتك جزءًا من سجل المراجعة.',
  'Enter the reviewer name to record this decision.':'أدخل اسم المراجع لتسجيل هذا القرار.',
  'The rule configuration must be valid JSON. Check commas, quotes, and brackets.':'يجب أن تكون إعدادات القاعدة بصيغة JSON صحيحة. تحقق من الفواصل وعلامات الاقتباس والأقواس.',
  'Saved results are available. Connecting starts a new inspection scope.':'النتائج المحفوظة متاحة. ينشئ الاتصال نطاق فحص جديدًا.',
  'Inspection, review, and checks require a connected source.':'يتطلب الفحص والمراجعة وتشغيل القواعد مصدرًا متصلًا.'
});
const englishTranslations = Object.fromEntries(Object.entries(uiTranslations).map(([english, arabic]) => [arabic, english]));
const translationSources = new WeakMap();
const preservedContent = 'script, style, input, textarea, code, pre, .code, .mono, .target, .relationship, [dir="ltr"], [translate="no"]';

function translatedText(text, translations) {
  let result = text;
  if (translations === uiTranslations) {
    result = result.replace(/\b(\d[\d,]*)\s+(tables|rows|columns)\b/giu, (_match, count, unit) => {
      const amount = Number(count.replaceAll(',', ''));
      const arabicUnit = unit.toLowerCase() === 'rows'
        ? amount >= 3 && amount <= 10 ? 'صفوف' : 'صف'
        : unit.toLowerCase() === 'columns'
          ? amount >= 3 && amount <= 10 ? 'أعمدة' : 'عمود'
          : 'جدول';
      return `${count} ${arabicUnit}`;
    });
  }
  const trimmed = result.trim();
  if (translations[trimmed]) return result.replace(trimmed, translations[trimmed]);
  for (const [source, replacement] of Object.entries(translations).sort((left, right) => right[0].length - left[0].length)) {
    const escaped = source.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(`(?<![\\p{L}\\p{N}_])${escaped}(?![\\p{L}\\p{N}_])`, 'giu');
    result = result.replace(pattern, replacement);
  }
  return result;
}

function applyLanguage(root = document) {
  const language = document.documentElement.lang === 'ar' ? 'ar' : 'en';
  // Always translate from the original chrome text. Reverse translation loses
  // information when two English labels share the same Arabic translation.
  const localize = (node, key, value) => {
    const records = translationSources.get(node) || {};
    let record = records[key];
    if (!record || value !== record.rendered) record = { source: translatedText(value, englishTranslations) };
    record.rendered = language === 'ar' ? translatedText(record.source, uiTranslations) : record.source;
    records[key] = record;
    translationSources.set(node, records);
    return record.rendered;
  };
  root.querySelectorAll?.('[data-en][data-ar]').forEach(element => {
    if (element.closest(preservedContent)) return;
    element.textContent = element.dataset[language];
  });
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (node.parentElement?.closest(`${preservedContent}, [data-en][data-ar]`)) continue;
    node.nodeValue = localize(node, 'text', node.nodeValue);
  }
  root.querySelectorAll?.('[aria-label], [placeholder], [title]').forEach(element => {
    if (element.closest('[translate="no"]')) return;
    for (const attribute of ['aria-label', 'placeholder', 'title']) {
      const value = element.getAttribute(attribute);
      if (value) element.setAttribute(attribute, localize(element, attribute, value));
    }
  });
  document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
  const languageButton = document.getElementById('langToggleBtn');
  if (languageButton) {
    languageButton.textContent = language === 'ar' ? 'EN' : 'عربي';
    languageButton.setAttribute('aria-label', language === 'ar' ? 'التبديل إلى الإنجليزية' : 'Switch to Arabic');
    languageButton.title = language === 'ar' ? 'التبديل إلى الإنجليزية' : 'Switch to Arabic';
  }
  const themeButton = document.getElementById('themeToggleBtn');
  if (themeButton) {
    themeButton.textContent = document.documentElement.dataset.theme === 'dark' ? '☼' : '☾';
    themeButton.setAttribute('aria-label', language === 'ar' ? 'تغيير المظهر' : 'Change theme');
    themeButton.title = language === 'ar' ? 'تغيير المظهر' : 'Change theme';
  }
  const refreshButton = document.getElementById('refresh');
  if (refreshButton) {
    refreshButton.setAttribute('aria-label', language === 'ar' ? 'تحديث مساحة العمل' : 'Refresh workspace');
    refreshButton.title = language === 'ar' ? 'تحديث مساحة العمل' : 'Refresh workspace';
  }
}

function toggleTheme() {
  const html = document.documentElement;
  html.dataset.theme = html.dataset.theme === 'light' ? 'dark' : 'light';
  try { localStorage.setItem('clarity_theme', html.dataset.theme); } catch { /* Optional preference. */ }
  applyLanguage();
}

function toggleLanguage() {
  const html = document.documentElement;
  html.lang = html.lang === 'ar' ? 'en' : 'ar';
  try { localStorage.setItem('clarity_language', html.lang); } catch { /* Optional preference. */ }
  applyLanguage();
}
const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
// Source identifiers, evidence and user-authored values are records, not UI copy.
const sourceText = value => `<span translate="no">${esc(value)}</span>`;
const list = value => Array.isArray(value) ? value : [];
const label = value => String(value ?? 'unavailable').replace(/_/g, ' ').replace(/^./, character => character.toUpperCase());
const num = value => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '—';
const percentage = value => typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value * 100)}%` : '—';
const score = value => typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value)}%` : '—';
const time = value => {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};
const badge = (status, text) => `<span class="badge ${esc(String(status || '').replace(/[^a-z_]/g, ''))}">${esc(text || label(status))}</span>`;
const target = proposal => [proposal?.target?.table, proposal?.target?.column].filter(Boolean).join('.') || 'Schema';
const currentProposals = () => list(app.state?.proposals).filter(proposal => proposal.current !== false);
const pendingProposals = () => currentProposals().filter(proposal => ['draft', 'needs_clarification'].includes(proposal.status));
const approvedRules = () => currentProposals().filter(proposal => proposal.status === 'approved' && proposal.kind === 'rule');
const connectedActions = new Set(['preflight', 'inspect', 'run', 'approve', 'edit', 'clarify', 'reject']);
const actionButton = (action, text, className = 'primary', extra = '') => `<button class="button ${className}" data-action="${esc(action)}" ${extra} ${app.busy || (connectedActions.has(action) && !app.state?.source?.connected) ? 'disabled' : ''}>${text}</button>`;
const empty = (title, description, control = '', icon = '▦') => `<div class="empty-state"><div class="empty-icon" aria-hidden="true">${icon}</div><h2>${esc(title)}</h2><p>${esc(description)}</p>${control}</div>`;
const heading = (eyebrow, title, description, actions = '') => `<div class="page-heading"><div><span class="eyebrow">${esc(eyebrow)}</span><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${actions ? `<div class="heading-actions">${actions}</div>` : ''}</div>`;
const metric = (title, value, note, symbol) => `<div class="metric-card"><div class="metric-top"><span>${esc(title)}</span><span class="metric-symbol" aria-hidden="true">${symbol}</span></div><div class="metric-value">${esc(value)}</div><div class="metric-note">${esc(note)}</div></div>`;

function reviewerName() {
  try { return localStorage.getItem('clarity-reviewer') || ''; } catch { return ''; }
}

function notify(message, isError = false) {
  const element = document.getElementById('notice');
  element.textContent = message;
  element.className = `notice${isError ? ' error' : ''}`;
  element.hidden = !message;
}

async function request(path, body) {
  const options = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); } catch { throw new Error('The server returned an unreadable response. Refresh and try again.'); }
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(item => item.msg || 'Invalid input').join('; ') : 'The request could not be completed.';
    throw new Error(message);
  }
  return data;
}

function updateHeader() {
  const state = app.state;
  document.getElementById('current-page').textContent = views[app.view];
  document.querySelectorAll('[data-view]').forEach(link => {
    const active = link.dataset.view === app.view;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  document.getElementById('queue-count').textContent = state ? num(pendingProposals().length) : '—';
  document.getElementById('source-status').innerHTML = !state ? 'Loading source…' : state.source?.mode === 'demo' ? 'Synthetic demo · local' : state.source?.connected ? state.source.name ? sourceText(state.source.name) : 'MySQL connected' : 'Source disconnected';
  const localProvider = state?.settings?.provider === 'local';
  document.getElementById('model-status').innerHTML = !state ? 'Checking model…' : state.settings?.configuration_error ? 'Check model configuration' : state.settings?.model_configured ? localProvider ? 'Local model configured · availability not tested' : `${sourceText(label(state.settings.provider))} · ${sourceText(state.settings.model)}` : `${sourceText(label(state.settings?.provider))} · credentials pending`;
  const sourceBadge = document.getElementById('sidebar-source');
  if (sourceBadge) sourceBadge.innerHTML = state?.source?.connected ? state.source.mode === 'mysql' ? `${sourceText(state.schema?.name || state.source.name)} · ${num(state.counts?.tables)} tables` : 'Demo' : 'Disconnected';
  const providerBadge = document.getElementById('sidebar-provider');
  if (providerBadge) providerBadge.innerHTML = state?.settings?.model_configured ? state.settings.provider === 'local' ? 'Local · configured' : sourceText(state.settings.provider) : 'Not configured';
  const indicator = document.getElementById('runtime-indicator');
  if (indicator) indicator.className = `status-indicator ${state?.source?.connected ? 'source-connected' : ''}`;
  const inspectCommand = document.getElementById('command-inspect');
  const runCommand = document.getElementById('command-run');
  if (inspectCommand) inspectCommand.disabled = app.busy || !state?.source?.connected;
  if (runCommand) runCommand.disabled = app.busy || !state?.source?.connected || approvedRules().length === 0;
  document.getElementById('refresh').disabled = app.busy;
}

function workflow() {
  const state = app.state;
  const inspected = list(state.inspections).length > 0;
  return `<div class="workflow-step"><span class="step-number ${state.source?.connected ? 'done' : ''}">${state.source?.connected ? '✓' : '01'}</span><div class="step-content"><h3>Connect a data source</h3><p>${state.source?.mode === 'demo' ? 'Synthetic records are ready for a complete local walkthrough.' : 'Use the configured, read-only MySQL source. Model processing begins only when you start an inspection.'}</p><div class="step-controls"><select class="control-select" id="source-mode" aria-label="Data source"><option value="mysql" ${state.source?.mode !== 'demo' ? 'selected' : ''}>MySQL · server environment</option><option value="demo" ${state.source?.mode === 'demo' ? 'selected' : ''}>Synthetic demo</option></select>${actionButton('connect', 'Connect source', 'secondary compact')}</div></div></div>
  <div class="workflow-step"><span class="step-number ${inspected ? 'done' : ''}">${inspected ? '✓' : '02'}</span><div class="step-content"><h3>Inspect and propose</h3><p>Inspect schema and bounded metrics to propose descriptions and quality rules.</p><div class="step-controls"><select class="control-select" id="inspection-mode" aria-label="Inspection mode" ${app.busy ? 'disabled' : ''}>${[['demo', 'Deterministic demo'], ['agent', 'Adaptive agent · model required'], ['fixed', 'Fixed workflow · model required']].map(([value, text]) => `<option value="${value}" ${app.inspectionMode === value ? 'selected' : ''}>${text}</option>`).join('')}</select>${actionButton('preflight', 'Check readiness', 'secondary compact')}${actionButton('inspect', app.busy ? 'Working…' : 'Start inspection', 'primary compact')}</div>${inspectionSettings()}</div></div>
  <div class="workflow-step"><span class="step-number">03</span><div class="step-content"><h3>Review the evidence</h3><p>Approve, edit, reject, or request clarification. Every edit creates a new draft version.</p><a class="button text compact" href="#review">Open review queue <span class="arrow">↗</span></a></div></div>
  <div class="workflow-step"><span class="step-number ${state.report ? 'done' : ''}">${state.report ? '✓' : '04'}</span><div class="step-content"><h3>Run approved checks</h3><p>Approval does not execute checks. Run the current approved rules when you are ready.</p>${actionButton('run', `Run approved checks (${approvedRules().length})`, 'secondary compact')}</div></div></div>`;
}

function miniProposal(proposal) {
  return `<div class="mini-proposal"><h3>${sourceText(proposal.title)}</h3><div class="mini-meta"><span class="target">${esc(target(proposal))}</span>${badge(proposal.status)}</div></div>`;
}

function reportFreshness(report) {
  if (!report?.outdated) return '';
  return `<div class="freshness-banner" role="status"><div><strong>Saved report is out of date</strong><p>The current approved rule versions differ from this report. The figures below remain the saved run snapshot. Run approved checks to refresh the report.</p></div>${actionButton('run', 'Refresh report', 'secondary compact')}</div>`;
}

function auditValue(value) {
  if (value == null || value === '') return 'Unknown';
  return sourceText(typeof value === 'object' ? JSON.stringify(value, null, 2) : value);
}

function checkDetails(result) {
  return `<details class="history check-details"><summary>Check definition and population</summary><div class="history-entry"><dl class="audit-facts"><div><dt>Approved version</dt><dd>${auditValue(result.version)}</dd></div><div><dt>Proposal ID</dt><dd class="mono">${auditValue(result.proposal_id)}</dd></div><div><dt>Metric</dt><dd>${auditValue(result.metric_id)}</dd></div><div><dt>Null handling</dt><dd>${auditValue(result.null_handling)}</dd></div><div><dt>Eligible population</dt><dd>${auditValue(result.eligible_population)}</dd></div></dl><strong>Parameters</strong><pre>${auditValue(result.parameters)}</pre></div></details>`;
}

function inspectionAudit() {
  const inspections = list(app.state.inspections);
  return `<section class="panel spacer-top"><div class="panel-header"><h2>Inspection audit</h2><small>${inspections.length} recorded runs · read-only</small></div>${inspections.length ? `<div class="panel-body">${inspections.map(inspection => {
    const usage = inspection.usage || {};
    const knownTokens = usage.usage_known !== false;
    const tokenValue = key => auditValue(knownTokens ? usage[key] : null);
    const estimatedCost = typeof usage.cost_usd === 'number' && Number.isFinite(usage.cost_usd) ? `$${usage.cost_usd.toFixed(6)}` : 'Unknown';
    return `<details class="inspection-audit"><summary><span><strong>${esc(label(inspection.mode || 'inspection'))}</strong><small>${esc(time(inspection.created_at))}</small></span>${badge(inspection.status)}</summary><div class="audit-body"><dl class="audit-facts"><div><dt>Run ID</dt><dd class="mono">${auditValue(inspection.id)}</dd></div><div><dt>Schema in this scope</dt><dd>${auditValue(app.state.schema?.name)}</dd></div><div><dt>Provider</dt><dd>${auditValue(inspection.provider)}</dd></div><div><dt>Model</dt><dd>${auditValue(inspection.model)}</dd></div><div><dt>Tool calls</dt><dd>${auditValue(usage.tool_calls)}</dd></div><div><dt>Model requests</dt><dd>${auditValue(usage.requests)}</dd></div><div><dt>Input tokens</dt><dd>${tokenValue('input_tokens')}</dd></div><div><dt>Output tokens</dt><dd>${tokenValue('output_tokens')}</dd></div><div><dt>Total tokens</dt><dd>${tokenValue('total_tokens')}</dd></div><div><dt>Cached input tokens</dt><dd>${auditValue(knownTokens && usage.cache_usage_known !== false ? usage.cached_tokens : null)}</dd></div><div><dt>Elapsed seconds</dt><dd>${auditValue(inspection.elapsed_seconds)}</dd></div><div><dt>Estimated cost</dt><dd>${esc(estimatedCost)}</dd></div></dl><p class="audit-note">${usage.pricing_basis ? sourceText(usage.pricing_basis) : 'Cost is unknown when no pricing estimate is recorded.'} Unknown usage is not counted as zero. Synthetic runs are demonstrations.</p><h3>Recorded limits</h3><pre>${auditValue(inspection.limits)}</pre><h3>Sanitized tool trace</h3>${list(inspection.trace).length ? inspection.trace.map((entry, index) => `<details class="trace-entry"><summary>${index + 1}. ${sourceText(entry.tool || 'Recorded call')} · ${esc(label(entry.status))}</summary><dl class="audit-facts"><div><dt>Target</dt><dd>${auditValue(entry.target)}</dd></div></dl><pre>${auditValue(entry.summary ?? entry)}</pre></details>`).join('') : '<p class="audit-note">No tool trace was recorded for this run.</p>'}</div></details>`;
  }).join('')}</div>` : empty('No inspection audit yet.', 'Run an inspection to record its model, usage, duration, and sanitized tool calls.', '<a class="button secondary" href="#overview">Inspect a source</a>', '⌁')}</section>`;
}

function renderOverview() {
  const state = app.state;
  const counts = state.counts || {};
  const pending = pendingProposals();
  const report = state.report;
  const inspections = list(state.inspections);
  return heading('YOUR GOVERNANCE WORKSPACE', 'A clearer picture of your data.', 'From schema to shared understanding. Inspect your source, review the evidence, and turn decisions into measurable quality.', `<a class="button secondary" href="#dictionary">▤ &nbsp; Data dictionary</a><a class="button primary" href="#review">Review proposals <span class="arrow">↗</span></a>`) +
  reportFreshness(report) + `<div class="welcome-banner"><div class="banner-content"><span class="eyebrow">${state.source?.mode === 'demo' ? 'SYNTHETIC DEMO WORKSPACE' : state.source?.connected ? 'CONNECTED DATA WORKSPACE' : 'YOUR LOCAL WORKSPACE'}</span><h2>${state.source?.mode === 'demo' ? 'Explore the full governance workflow.' : 'Bring your source into focus.'}</h2><p>${state.source?.mode === 'demo' ? 'A deterministic demonstration with synthetic records. Model-driven inspection and real evaluation trials remain separate and require configuration.' : 'Source data is read-only. Review proposals before explicitly running approved checks against this inspection scope.'}</p></div><div class="banner-graphic" aria-hidden="true"><span class="graphic-block">▦</span>→<span class="graphic-block">☑</span>→<span class="graphic-block final">✓</span></div></div>` +
  `<div class="metrics-grid">${metric('Tables in scope', num(counts.tables), 'From the connected schema', '▦')}${metric('Columns discovered', num(counts.columns), 'Ready for documentation', '▤')}${metric('Awaiting review', num(pending.length), 'Decisions need your attention', '☑')}${metric('Quality score', score(report?.summary?.overall_score), report ? `${percentage(report.summary?.coverage)} check coverage` : 'Run approved checks to measure', '◷')}</div>` +
  `<div class="grid-two"><div><section class="panel"><div class="panel-header"><h2>Your next steps</h2><small>Human review at every decision</small></div><div class="panel-body">${workflow()}</div></section></div><div><section class="panel"><div class="panel-header"><h2>Awaiting your review</h2>${badge('draft', `${pending.length} pending`)}</div>${pending.length ? pending.slice(0, 3).map(miniProposal).join('') : empty('A clean slate.', 'Start an inspection to surface proposals for review.', '', '☑')}<div class="panel-footer"><a class="button text" href="#review">View review queue <span class="arrow">→</span></a></div></section><section class="panel"><div class="panel-header"><h2>Inspection activity</h2><small>${inspections.length} recorded</small></div><div class="panel-body">${inspections.length ? inspections.slice(0, 3).map(inspection => `<div class="activity-row"><span class="activity-dot"></span><div><strong>${esc(label(inspection.mode || inspection.provider || 'inspection'))} ${inspection.status ? `· ${esc(label(inspection.status))}` : ''}</strong><small>${esc(time(inspection.created_at))}${inspection.elapsed_seconds != null ? ` · ${esc(inspection.elapsed_seconds)} seconds` : ''}</small></div></div>`).join('') : '<p>Inspection runs will appear here. No inspection has been recorded for this scope.</p>'}</div></section></div></div>`;
}

function renderSchema() {
  const schema = app.state.schema;
  return heading('KNOW YOUR SOURCE', 'Schema explorer', 'Explore the structure behind your data. Tables, types, and declared relationships come directly from the connected source.', `<a class="button primary" href="#overview">Inspect source <span class="arrow">↗</span></a>`) +
  (!schema ? `<section class="panel">${empty('No schema loaded', 'Connect a source from the overview to discover its tables and columns.', '<a class="button primary" href="#overview">Connect a source</a>')}</section>` :
  `<div class="toolbar"><span class="muted">${sourceText(schema.name || app.state.source?.name)} · ${list(schema.tables).length} tables</span><input class="search-input" data-search="schema" type="search" placeholder="Search tables and columns…" aria-label="Search schema" value="${esc(app.search)}"></div>` +
  list(schema.tables).filter(table => !app.search || `${table.name} ${list(table.columns).map(column => column.name).join(' ')}`.toLowerCase().includes(app.search.toLowerCase())).map(table => `<details class="panel schema-table" open><summary><strong>${sourceText(table.name)}</strong><small>${num(table.row_count)} rows · ${list(table.columns).length} columns</small></summary><div class="table-scroll"><table><thead><tr><th>Column</th><th>Data type</th><th>Nullable</th><th>Key</th></tr></thead><tbody>${list(table.columns).map(column => `<tr><td class="code">${esc(column.name)}</td><td>${sourceText(column.data_type)}</td><td>${column.nullable ? 'Yes' : 'No'}</td><td>${sourceText(column.key || '—')}</td></tr>`).join('')}</tbody></table></div></details>`).join('') +
  (list(schema.relationships).length ? `<section class="panel"><div class="panel-header"><h2>Declared relationships</h2><small>Source metadata</small></div><div class="panel-body">${schema.relationships.map(relationship => `<div class="relationship">${esc(typeof relationship === 'string' ? relationship : JSON.stringify(relationship))}</div>`).join('')}</div></section>` : '<div class="inline-note">No declared relationships were returned by this schema.</div>'));
}

function proposalHistory(proposal) {
  const history = list(proposal.history);
  return `<details class="history"><summary>Version ${esc(proposal.version)} · ${history.length ? `${history.length} preserved ${history.length === 1 ? 'version' : 'versions'}` : 'View provenance'}</summary><div class="history-entry">Current version created ${esc(time(proposal.created_at))}${proposal.reviewer ? `<br>Reviewed by ${sourceText(proposal.reviewer)} · ${esc(time(proposal.reviewed_at))}` : ''}</div>${history.map(entry => `<div class="history-entry">${typeof entry === 'string' ? sourceText(entry) : `<strong>Version ${esc(entry.version ?? '—')} · ${esc(label(entry.status))}</strong>${entry.title ? `<br>${sourceText(entry.title)}` : ''}${entry.description ? `<br>${sourceText(entry.description)}` : ''}${list(entry.reviews).map(review => `<div class="review-event">${esc(label(review.action))} · ${sourceText(review.reviewer)} · ${esc(time(review.created_at))}${review.note ? `<br>${sourceText(review.note)}` : ''}${typeof review.review_seconds === 'number' ? `<br>${Math.round(review.review_seconds)} seconds in review interaction` : ''}</div>`).join('')}${entry.rule ? `<details><summary>Preserved rule configuration</summary><pre>${esc(JSON.stringify(entry.rule, null, 2))}</pre></details>` : ''}${entry.note ? `<br>${sourceText(entry.note)}` : ''}`}</div>`).join('')}${proposal.original ? `<div class="history-entry"><strong>Original proposal</strong><br>${sourceText(proposal.original.title || '')}<br>${sourceText(proposal.original.description || '')}</div>` : ''}</details>`;
}

function proposalCard(proposal) {
  const editable = ['draft', 'needs_clarification', 'approved'].includes(proposal.status);
  const reviewable = ['draft', 'needs_clarification'].includes(proposal.status);
  const approvable = proposal.status === 'draft';
  const attributes = `data-id="${esc(proposal.id)}"`;
  const column = list(app.state?.schema?.tables).find(table => table.name === proposal.target?.table)?.columns?.find(item => item.name === proposal.target?.column);
  return `<article class="proposal-card" data-status="${esc(proposal.status)}"><div class="proposal-heading"><div class="proposal-title"><span class="proposal-icon" aria-hidden="true">${proposal.kind === 'rule' ? '⌁' : '▤'}</span><div><h2>${sourceText(proposal.title)}</h2><div class="proposal-meta"><span class="code-token" dir="ltr">${esc(target(proposal))}</span><span class="badge">${column?.data_type ? sourceText(column.data_type) : esc(label(proposal.kind))}</span><span class="badge">v${esc(proposal.version)}</span></div></div></div>${badge(proposal.status)}</div><p class="proposal-description">${proposal.description ? sourceText(proposal.description) : 'No description provided.'}</p><div class="proposal-evidence-grid"><div class="evidence-box"><strong>EVIDENCE</strong>${list(proposal.evidence).length ? `<ul>${proposal.evidence.map(item => `<li>${sourceText(item)}</li>`).join('')}</ul>` : '<p>No evidence was supplied. Clarify assumptions before approval.</p>'}${list(proposal.assumptions).length ? `<strong>ASSUMPTIONS</strong><ul>${proposal.assumptions.map(item => `<li>${sourceText(item)}</li>`).join('')}</ul>` : ''}</div>${proposal.rule ? `<details class="history rule-history" open><summary>Proposed rule · configuration</summary><div class="history-entry"><pre>${esc(JSON.stringify(proposal.rule, null, 2))}</pre></div></details>` : ''}</div><div class="proposal-footer"><div class="proposal-actions">${approvable ? actionButton('approve', '✓ &nbsp; Approve', 'soft compact', attributes) : ''}${editable ? actionButton('edit', 'Edit proposal', 'secondary compact', attributes) : ''}${reviewable ? actionButton('clarify', 'Clarify', 'secondary compact', attributes) + actionButton('reject', 'Reject', 'danger compact', attributes) : ''}</div></div><div class="proposal-history">${proposalHistory(proposal)}</div></article>`;
}
function renderReview() {
  const proposals = currentProposals();
  const filtered = proposals.filter(proposal => app.filter === 'all' || (app.filter === 'pending' ? ['draft', 'needs_clarification'].includes(proposal.status) : proposal.status === app.filter));
  return heading('EVIDENCE BEFORE ACTION', 'Review queue', 'Every proposal is a starting point. Review the evidence and assumptions, then decide what belongs in your governance standard.') +
  `<div class="toolbar"><div class="tabs" role="group" aria-label="Filter proposals">${[['pending', 'Awaiting review'], ['approved', 'Approved'], ['all', 'All proposals']].map(([filter, text]) => `<button class="tab ${app.filter === filter ? 'active' : ''}" data-filter="${filter}" aria-pressed="${app.filter === filter}">${text} <span>${filter === 'pending' ? pendingProposals().length : filter === 'approved' ? proposals.filter(proposal => proposal.status === 'approved').length : proposals.length}</span></button>`).join('')}</div><label class="reviewer-box">Reviewer <input id="reviewer-name" autocomplete="name" placeholder="Your name" value="${esc(reviewerName())}" aria-label="Reviewer name"></label></div><div class="inline-note">Approving a rule records your decision. Checks run only when you select “Run approved checks.” Edited proposals become new draft versions and require approval again.</div>` +
  (filtered.length ? filtered.map(proposalCard).join('') : `<section class="panel">${empty(app.filter === 'pending' ? 'Nothing awaiting review.' : 'No proposals in this view.', app.filter === 'pending' ? 'Start an inspection to create proposals, or view approved decisions in the next tab.' : 'Proposals will appear here after inspection and review.', '<a class="button secondary" href="#overview">Back to overview</a>', '☑')}</section>`);
}

function renderDictionary() {
  const dictionary = app.dictionary;
  const columns = list(dictionary?.columns).filter(column => !app.search || `${column.table} ${column.column} ${column.description || ''}`.toLowerCase().includes(app.search.toLowerCase()));
  if (!app.state.schema) return heading('A SHARED LANGUAGE', 'Data dictionary', 'Connect a source to build a reference for its schema and reviewed descriptions.') + `<section class="panel">${empty('No source connected', 'Connect a source from the overview to load its dictionary.', '<a class="button primary" href="#overview">Connect a source</a>', '▤')}</section>`;
  return heading('A SHARED LANGUAGE', 'Data dictionary', 'A living reference for your schema, with proposed and approved descriptions clearly identified.', `<a class="button secondary" href="/api/export/dictionary" download>↓ &nbsp; Export CSV</a>`) +
  (app.dictionaryLoading ? '<section class="panel"><div class="loading-state compact-loading"><span class="spinner"></span><p>Loading dictionary…</p></div></section>' : !dictionary ? `<section class="panel">${empty('Dictionary could not be loaded', 'Refresh this view to request the dictionary from the server.', actionButton('dictionary-refresh', 'Try again', 'secondary'), '▤')}</section>` :
  `<div class="toolbar"><span class="muted">${dictionary.columns?.length || 0} columns · source descriptions and review status</span><input class="search-input" data-search="dictionary" type="search" placeholder="Search the dictionary…" aria-label="Search dictionary" value="${esc(app.search)}"></div><section class="panel">${columns.length ? `<div class="table-scroll"><table><thead><tr><th>Table / column</th><th>Type</th><th>Description</th><th>Review status</th><th>Version</th></tr></thead><tbody>${columns.map(column => `<tr><td class="code"><span translate="no">${esc(column.column)}</span><small translate="no">${esc(column.table)}</small></td><td>${sourceText(column.data_type)}<small>${column.nullable ? 'Nullable' : 'Not nullable'}${column.key ? ` · ${sourceText(column.key)}` : ''}</small></td><td class="description">${column.description ? sourceText(column.description) : 'No reviewed description yet'}${list(column.evidence).length ? `<details class="history"><summary>Description evidence</summary><div class="history-entry">${column.evidence.map(sourceText).join('<br>')}</div></details>` : ''}</td><td>${badge(column.status)}</td><td>${column.version != null ? `v${esc(column.version)}` : '—'}</td></tr>`).join('')}</tbody></table></div>` : empty('No columns to show.', app.search ? 'Try a different search term.' : 'Connect a source and inspect its schema to build your dictionary.', '', '▤')}</section>`);
}

function dimensionRows(summary) {
  return ['completeness', 'uniqueness', 'validity', 'consistency'].map(name => {
    const dimension = summary.dimensions?.[name];
    const value = typeof dimension === 'number' ? dimension : dimension?.score ?? dimension?.overall_score;
    const width = typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
    return `<div class="dimension"><div class="dimension-head"><span>${esc(label(name))}</span><strong>${score(value)}</strong></div><progress class="bar" max="100" value="${width}" aria-label="${esc(label(name))} score">${score(value)}</progress>${dimension && typeof dimension === 'object' && dimension.status ? `<small class="muted">${esc(label(dimension.status))}${dimension.coverage != null ? ` · ${percentage(dimension.coverage)} coverage` : ''}</small>` : ''}</div>`;
  }).join('');
}

function renderQuality() {
  const report = app.state.report;
  const summary = report?.summary || {};
  const overall = typeof summary.overall_score === 'number' && Number.isFinite(summary.overall_score) ? Math.max(0, Math.min(100, summary.overall_score)) : 0;
  const unresolved = report?.unresolved;
  return heading('MEASURE WHAT MATTERS', 'Quality report', 'Quality scores reflect completed, eligible checks. Coverage and unresolved outcomes stay visible alongside the score.', actionButton('run', app.busy ? 'Running checks…' : `Run approved checks (${approvedRules().length})`) + (report ? '<a class="button secondary" href="/api/export/report" download>↓ &nbsp; Export JSON</a>' : '')) +
  reportFreshness(report) + (!report ? `<section class="panel">${empty('Your first quality report starts here.', 'Review and approve rule proposals, then explicitly run the checks. No quality score has been measured in this scope.', '<a class="button secondary" href="#review">Review proposals</a>', '◷')}</section>` :
  `<section class="panel"><div class="panel-header"><h2>Quality at a glance</h2>${badge(summary.status)}</div><div class="panel-body"><div class="quality-overview"><div class="score-ring"><svg class="ring-visual" viewBox="0 0 160 160" aria-hidden="true"><circle class="ring-track" cx="80" cy="80" r="73"/><circle class="ring-value" cx="80" cy="80" r="73" pathLength="100" stroke-dasharray="${overall} 100"/></svg><div class="score-inner"><strong>${score(summary.overall_score)}</strong><small>overall quality</small></div></div><div>${dimensionRows(summary)}</div></div><div class="report-meta"><span>Check coverage <strong>${percentage(summary.coverage)}</strong></span><span>Completed <strong>${num(summary.completed_checks)}</strong> / applicable <strong>${num(summary.applicable_checks)}</strong></span><span>Generated ${esc(time(report.created_at))}</span><span>Source ${sourceText(report.source?.name)} · ${esc(label(report.source?.mode))}</span><span>Profiled columns ${num(report.profiled_columns)} / selected ${num(report.selected_columns)}</span></div></div></section><div class="inline-note">Scores use passing and eligible records from completed checks. Failed, unrun, inapplicable, and empty-data outcomes retain their status; missing scores are shown as “—”.</div><section class="panel"><div class="panel-header"><h2>Check results</h2><small>${list(report.results).length} recorded results</small></div>${list(report.results).length ? `<div class="table-scroll"><table><thead><tr><th>Check / target</th><th>Dimension</th><th>Status</th><th>Eligible</th><th>Passing</th><th>Violations</th></tr></thead><tbody>${report.results.map(result => `<tr><td class="description">${sourceText(result.title || label(result.metric_id))}<small class="mono">${esc(target(result))} · v${esc(result.version ?? '—')}</small>${result.reason ? `<small>${sourceText(result.reason)}</small>` : ''}${checkDetails(result)}${list(result.violation_ids).length ? `<details class="history"><summary>Violation references</summary><div class="history-entry mono">${esc(JSON.stringify(result.violation_ids))}</div></details>` : ''}</td><td>${esc(label(result.dimension))}</td><td>${badge(result.status)}</td><td>${num(result.eligible)}</td><td>${num(result.passing)}</td><td>${num(result.violations)}</td></tr>`).join('')}</tbody></table></div>` : empty('No approved checks were executed.', 'Approve rule proposals and run the checks again to populate measurable results.', '', '◷')}</section><section class="panel"><div class="panel-header"><h2>Unresolved outcomes</h2><small>Preserved in the exported report</small></div><div class="panel-body">${unresolved == null ? '<p>No unresolved summary was returned.</p>' : Array.isArray(unresolved) ? unresolved.length ? unresolved.map(item => `<div class="history-entry">${sourceText(typeof item === 'string' ? item : JSON.stringify(item))}</div>`).join('') : '<p>No unresolved outcomes were recorded.</p>' : typeof unresolved === 'object' ? `<div class="report-meta unresolved-meta">${Object.entries(unresolved).map(([key, value]) => `<span>${esc(label(key))}: <strong>${sourceText(typeof value === 'object' ? JSON.stringify(value) : value)}</strong></span>`).join('')}</div>` : `<p>${num(unresolved)} proposals awaiting review or clarification.</p>`}</div></section>`);
}

function renderEvaluation() {
  const evaluation = app.state.evaluation || {};
  return heading('VALIDATE WITH REAL EVIDENCE', 'Evaluation readiness', 'A working demonstration establishes the workflow. Research results require independent trials and a reviewed reference.') +
  `<div class="welcome-banner"><div class="banner-content"><span class="eyebrow">RESEARCH STATUS</span><h2>${esc(label(evaluation.status || 'pending'))}</h2><p>${evaluation.message ? sourceText(evaluation.message) : 'Real provider trials, reference review, and frozen thresholds are pending. No research performance claim has been established.'}</p></div></div><div class="evaluation-grid"><section class="evaluation-card"><span class="metric-symbol">▦</span><h3>Synthetic demonstration</h3><p>Exercise connection, inspection, review, checks, and exports using deterministic synthetic records.</p>${badge('synthetic', 'Demonstration only')}</section><section class="evaluation-card"><span class="metric-symbol">⌁</span><h3>Provider trials</h3><p>Run independent adaptive and fixed workflow trials with the configured model. Cached repeats are not independent trials.</p>${badge(app.state.settings?.model_configured ? 'draft' : 'unavailable', app.state.settings?.model_configured ? 'Configuration present · trials pending' : 'Credentials pending')}</section><section class="evaluation-card"><span class="metric-symbol">☑</span><h3>Human reference review</h3><p>Compare deduplicated detections against a reviewed reference and advisor-approved, frozen targets.</p>${badge('draft', 'External review required')}</section></div><section class="panel spacer-top"><div class="panel-header"><h2>Before final evaluation</h2><small>Evidence required</small></div><div class="panel-body"><ul class="evaluation-list"><li>A real MySQL test source and model-provider configuration</li><li>Human-reviewed reference annotations and detection targets</li><li>Advisor-approved frozen thresholds and a recorded configuration</li><li>Independent, uncached adaptive and fixed workflow trials</li><li>Precision, recall, efficiency, and coverage reported with provenance</li></ul><div class="inline-note">Synthetic demo runs are never counted as live model runs or independent evaluation trials. Model configuration alone does not establish successful provider access.</div></div></section>` + inspectionAudit();
}

function renderPrivacy() {
  const privacy = app.state.privacy || {};
  const policy = privacy.policy || {};
  const sampling = policy.sampling || {};
  const runs = list(privacy.runs);
  return heading('CONTROL WHAT LEAVES YOUR SOURCE', 'Privacy controls', 'Values stay in your database. The model receives schema, aggregate counts, and bounded shape descriptors.', '<a class="button secondary" href="/api/export/privacy" download>Export privacy report</a>') +
    `<div class="welcome-banner"><div class="banner-content"><span class="eyebrow">${policy.version ? sourceText(policy.version) : 'Policy unavailable'}</span><h2>${policy.configuration_error ? 'Review privacy configuration' : 'Full value redaction is active.'}</h2><p>${policy.configuration_error ? sourceText(policy.configuration_error) : 'Email addresses, phone numbers, IDs, dates, and free text are withheld as values. Text lengths are generalized into ranges. Names of tables and columns, and exact aggregate counts, remain visible.'}</p></div></div>` +
    `<div class="metrics-grid">${metric('Raw value policy', policy.raw_values_allowed === false ? 'Withheld' : 'Unknown', 'No partial email or phone fragments', '◇')}${metric('Sample cap', num(sampling.max_samples), `${percentage(sampling.rate)} target · per column request`, '▦')}${metric('Requests checked', num(privacy.checked_requests), 'Outbound history passed the gate', '✓')}${metric('Requests blocked', num(privacy.blocked_requests), 'Stopped before provider submission', '⊘')}</div>` +
    `<div class="grid-two"><section class="panel"><div class="panel-header"><h2>What the model can see</h2></div><div class="panel-body"><ul class="evaluation-list"><li>Table and column names, types, nullability, and declared relationships</li><li>Aggregate counts, including missing and distinct-value counts</li><li>Value types and length ranges, such as string / 9–16 characters</li></ul><p>Raw samples, source comments, row identifiers, credentials, and error details are excluded.</p></div></section><section class="panel"><div class="panel-header"><h2>Sampling and limits</h2></div><div class="panel-body"><p>Choose up to ${esc(num(sampling.max_samples))} descriptors from a pool of at most ${esc(num(sampling.candidate_pool))}. A fixed seed makes selection repeatable; this is a bounded sample, not a uniform sample of the entire table.</p><p>Quality checks still use their full eligible populations. Sampling affects model examples only.</p><div class="inline-note">Accuracy retention has not been measured. These controls are not an anonymity or compliance certification.</div></div></section></div>` +
    `<section class="panel spacer-top"><div class="panel-header"><h2>Outbound privacy audit</h2><small>${runs.length} recorded inspections</small></div>${runs.length ? `<div class="table-scroll"><table><thead><tr><th>Provider / model</th><th>Status</th><th>Checked requests</th><th>Blocked requests</th><th>Shape submissions</th></tr></thead><tbody>${runs.map(run => `<tr><td>${sourceText(run.provider)}<br><small>${sourceText(run.model)}</small></td><td>${badge(run.status)}</td><td>${esc(num(run.checked_requests))}</td><td>${esc(num(run.blocked_requests))}</td><td>${esc(num(run.shape_descriptors_submitted))}</td></tr>`).join('')}</tbody></table></div><div class="panel-footer"><p>Submissions count descriptors included in request history, including retries. They are not unique source rows.</p></div>` : empty('No audited inspection yet', 'Model requests will be counted when an inspection reaches the provider. Configuration alone does not make a request.', '<a class="button secondary" href="#overview">Go to inspections</a>', '◇')}</section>` +
    (privacy.legacy_runs_without_audit ? `<p class="muted">${esc(num(privacy.legacy_runs_without_audit))} older runs have no privacy audit and are excluded from these counters.</p>` : '');
}

function inspectionSettings() {
  const fields = [
    ['max_calls', 'Tool calls', 1, 500], ['max_steps', 'Model steps', 1, 32],
    ['max_seconds', 'Seconds', 1, 600], ['max_tokens', 'Total tokens', 1, 200000],
    ['max_output_tokens', 'Output tokens / request', 1, 16000], ['max_retries', 'Retries', 0, 3]
  ];
  const columns = list(app.state?.schema?.tables).reduce((count, table) => count + list(table.columns).length, 0);
  return `<details class="inspection-settings"><summary>Inspection limits</summary><p>A full fixed pass of ${num(columns)} columns needs ${num(columns + 1)} tool calls. Time and token limits can still stop a run. Larger limits may increase API cost.</p><div class="budget-grid">${fields.map(([key, title, min, max]) => `<label for="limit-${key}">${title}<input class="control-select" id="limit-${key}" data-limit="${key}" type="number" min="${min}" max="${max}" step="1" value="${esc(app.limits[key])}" ${app.busy ? 'disabled' : ''}></label>`).join('')}</div></details><div id="inspection-readiness" role="status">${readinessMessage()}</div>`;
}

function readinessMessage() {
  if (!app.preflight) return '';
  const check = app.preflight;
  const heading = !check.ready ? 'Not ready to start' : check.mode === 'demo' ? 'Local checks passed' : 'Configuration present · provider not tested';
  return `<div class="readiness-result"><strong>${heading}</strong>${list(check.issues).map(issue => `<p>${esc(issue.message)}</p>`).join('')}<p>${esc(check.note)}</p></div>`;
}

async function prepareInspection(start) {
  if (app.busy || !app.state?.source?.connected) return;
  const body = { mode: app.inspectionMode, limits: { ...app.limits } };
  app.busy = true;
  app.preflight = null;
  notify('');
  render();
  try {
    app.preflight = await request('/api/inspect/preflight', body);
    if (start && app.preflight.ready) {
      app.state = await request('/api/inspect', body);
      app.dictionary = null;
      notify('Inspection recorded. Review its status, evidence, and proposals.');
    }
  } catch (error) { notify(error.message, true); }
  finally { app.busy = false; render(); }
}

function render() {
  updateHeader();
  if (!app.state) { applyLanguage(); return; }
  const renderers = { overview: renderOverview, schema: renderSchema, review: renderReview, dictionary: renderDictionary, quality: renderQuality, evaluation: renderEvaluation, privacy: renderPrivacy };
  const savedResults = app.state.schema && !app.state.source?.connected ? '<div class="inline-note" role="status"><strong>Saved results are available. Connecting starts a new inspection scope.</strong><br>Inspection, review, and checks require a connected source.</div>' : '';
  main.innerHTML = savedResults + renderers[app.view]();
  applyLanguage();
}

async function loadDictionary() {
  if (app.dictionaryLoading || !app.state?.schema) return;
  app.dictionaryLoading = true;
  if (app.view === 'dictionary') render();
  try { app.dictionary = await request('/api/dictionary'); }
  catch (error) { notify(error.message, true); }
  finally { app.dictionaryLoading = false; if (app.view === 'dictionary') render(); }
}

async function loadState() {
  if (app.busy) return;
  app.preflight = null;
  app.busy = true;
  updateHeader();
  try {
    app.state = await request('/api/state');
    app.dictionary = null;
    notify('');
    render();
  } catch (error) {
    notify(error.message, true);
    if (!app.state) main.innerHTML = `<section class="panel">${empty('Workspace unavailable', 'The local server could not load the workspace. Make sure it is running, then try again.', '<button class="button primary" data-action="retry">Try again</button>')}</section>`;
  } finally {
    app.busy = false;
    if (app.state) render(); else updateHeader();
    if (app.view === 'dictionary' && app.state) loadDictionary();
  }
}

async function mutate(path, body, message) {
  if (app.busy) return false;
  app.preflight = null;
  app.busy = true;
  notify('Working… This action can take a moment.');
  render();
  try {
    app.state = await request(path, body);
    app.dictionary = null;
    notify(message);
    return true;
  } catch (error) { notify(error.message, true); return false; }
  finally { app.busy = false; render(); if (app.view === 'dictionary') loadDictionary(); }
}

function setView() {
  const view = location.hash.slice(1);
  app.view = Object.hasOwn(views, view) ? view : 'overview';
  app.search = '';
  render();
  if (app.view === 'dictionary' && app.state && !app.dictionary) loadDictionary();
}

function field(name, title, value, textarea = false, hint = '', css = '') {
  return `<label class="field">${esc(title)}${textarea ? `<textarea name="${esc(name)}" class="${css}">${esc(value)}</textarea>` : `<input name="${esc(name)}" value="${esc(value)}" ${name === 'reviewer' ? 'required autocomplete="name"' : name === 'title' ? 'required' : ''}>`}${hint ? `<span class="field-hint">${esc(hint)}</span>` : ''}</label>`;
}

function openReview(action, id) {
  if (app.busy || !app.state?.source?.connected) return;
  const proposal = currentProposals().find(item => String(item.id) === id);
  if (!proposal) { notify('This proposal is no longer available. Refresh the workspace.', true); return; }
  app.dialog = { action, proposal, openedAt: performance.now() };
  document.getElementById('dialog-title').textContent = action === 'edit' ? 'Edit proposal · create a new draft' : `${label(action)} proposal`;
  document.getElementById('dialog-submit').textContent = action === 'edit' ? 'Save new draft' : action === 'clarify' ? 'Request clarification' : `${label(action)} proposal`;
  document.getElementById('dialog-submit').className = `button ${action === 'reject' ? 'danger' : 'primary'}`;
  document.getElementById('dialog-content').innerHTML = `<p class="dialog-summary"><strong>${sourceText(proposal.title)}</strong><br><span class="target">${esc(target(proposal))} · version ${esc(proposal.version)}</span></p>${field('reviewer', 'Reviewer name', reviewerName())}${action === 'edit' ? field('title', 'Title', proposal.title) + field('description', 'Description', proposal.description, true) + field('evidence', 'Evidence', list(proposal.evidence).join('\n'), true, 'One item per line. Preserve the evidence used to reach this decision.') + field('assumptions', 'Assumptions', list(proposal.assumptions).join('\n'), true, 'One assumption per line.') + (proposal.kind === 'rule' ? field('rule', 'Executable rule · JSON', JSON.stringify(proposal.rule, null, 2), true, 'Use metric_id, target, and parameters. The server validates the configuration before saving.', 'json-input') : '') : ''}${field('note', action === 'clarify' ? 'Clarification request' : 'Review note', '', true, action === 'approve' ? 'Approval records the decision. It does not run checks.' : action === 'edit' ? 'The current version is preserved. Your edit creates a new draft requiring approval.' : 'Your note becomes part of the review history.')}`;
  document.getElementById('dialog-error').hidden = true;
  applyLanguage(dialog);
  dialog.showModal();
}

document.getElementById('proposal-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!app.dialog || app.busy || !app.state?.source?.connected) return;
  const { action, proposal, openedAt } = app.dialog;
  const form = new FormData(event.currentTarget);
  const reviewer = String(form.get('reviewer') || '').trim();
  const errorElement = document.getElementById('dialog-error');
  const body = { action, reviewer, note: String(form.get('note') || '').trim(), review_seconds: Math.max(0, (performance.now() - openedAt) / 1000) };
  try {
    if (!reviewer) throw new Error('Enter the reviewer name to record this decision.');
    if (action === 'edit') {
      const split = name => String(form.get(name) || '').split('\n').map(item => item.trim()).filter(Boolean);
      body.changes = { title: String(form.get('title') || '').trim(), description: String(form.get('description') || '').trim(), evidence: split('evidence'), assumptions: split('assumptions') };
      if (proposal.kind === 'rule') {
        try { body.changes.rule = JSON.parse(String(form.get('rule'))); }
        catch { throw new Error('The rule configuration must be valid JSON. Check commas, quotes, and brackets.'); }
      }
    }
    errorElement.hidden = true;
    app.busy = true;
    document.getElementById('dialog-submit').disabled = true;
    app.state = await request(`/api/proposals/${encodeURIComponent(proposal.id)}/review`, body);
    app.dictionary = null;
    try { localStorage.setItem('clarity-reviewer', reviewer); } catch { /* Optional local convenience. */ }
    dialog.close();
    app.dialog = null;
    notify(action === 'edit' ? 'New draft saved. Review and approve the new version before it can activate.' : action === 'approve' ? 'Proposal approved. Run approved checks explicitly when you are ready.' : action === 'clarify' ? 'Clarification requested and recorded in history.' : 'Proposal rejected and recorded in history.');
  } catch (error) { errorElement.textContent = error.message; errorElement.hidden = false; }
  finally { app.busy = false; document.getElementById('dialog-submit').disabled = false; render(); }
});

main.addEventListener('click', async event => {
  const filter = event.target.closest('[data-filter]');
  if (filter) { app.filter = filter.dataset.filter; render(); return; }
  const control = event.target.closest('[data-action]');
  if (!control || control.disabled || app.busy) return;
  const action = control.dataset.action;
  if (['approve', 'reject', 'clarify', 'edit'].includes(action)) { openReview(action, control.dataset.id); return; }
  if (action === 'connect') {
    const mode = document.getElementById('source-mode')?.value || 'demo';
    await mutate('/api/connect', { mode }, 'Source connected. A fresh inspection scope is ready.');
  } else if (action === 'inspect' || action === 'preflight') {
    await prepareInspection(action === 'inspect');
  } else if (action === 'run') {
    await mutate('/api/checks/run', {}, 'Checks recorded. Open the quality report to review scores, coverage, and unresolved outcomes.');
  } else if (action === 'retry') { await loadState(); }
  else if (action === 'dictionary-refresh') { await loadDictionary(); }
});

main.addEventListener('input', event => {
  if (event.target.dataset.limit || event.target.id === 'inspection-mode') {
    if (event.target.dataset.limit) app.limits[event.target.dataset.limit] = event.target.value === '' ? null : Number(event.target.value);
    else app.inspectionMode = event.target.value;
    app.preflight = null;
    const readiness = document.getElementById('inspection-readiness');
    if (readiness) readiness.textContent = '';
  }
  if (event.target.id === 'reviewer-name') {
    try { localStorage.setItem('clarity-reviewer', event.target.value); } catch { /* Optional local convenience. */ }
  }
  if (event.target.matches('[data-search]')) {
    app.search = event.target.value;
    const selection = event.target.selectionStart;
    render();
    const replacement = main.querySelector('[data-search]');
    replacement?.focus();
    // Search inputs may not support selection ranges in every browser.
    try { replacement?.setSelectionRange(selection, selection); } catch { /* Focus remains on the search field. */ }
  }
});

function closeDialog() { if (!app.busy) { dialog.close(); app.dialog = null; } }
document.getElementById('close-dialog').addEventListener('click', closeDialog);
document.getElementById('cancel-dialog').addEventListener('click', closeDialog);
dialog.addEventListener('cancel', event => { if (app.busy) event.preventDefault(); else app.dialog = null; });
document.getElementById('refresh').addEventListener('click', loadState);
document.getElementById('themeToggleBtn').addEventListener('click', toggleTheme);
document.getElementById('langToggleBtn').addEventListener('click', toggleLanguage);
document.getElementById('command-inspect').addEventListener('click', () => prepareInspection(true));
document.getElementById('command-run').addEventListener('click', () => mutate('/api/checks/run', {}, 'Checks recorded. Open the quality report to review scores, coverage, and unresolved outcomes.'));
window.addEventListener('hashchange', setView);
setView();
loadState();
applyLanguage();
