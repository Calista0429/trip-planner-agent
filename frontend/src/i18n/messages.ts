// UI string dictionary. Only static interface chrome lives here; the generated
// trip text returned by the backend (attraction names, descriptions, weather,
// overall suggestions) is LLM Chinese and is rendered as-is regardless of locale.

export type Locale = 'zh' | 'en'

export interface Messages {
  app: Record<string, string>
  home: Record<string, string>
  result: Record<string, string>
}

const zh: Messages = {
  app: {
    brand: 'HelloAgents 智能旅行助手',
    footer: 'HelloAgents 智能旅行助手 ©2026',
    langLabel: '语言'
  },
  home: {
    bannerTitle: '创建一份可执行的旅行计划',
    bannerSubtitle: '输入目的地、日期、同行人数和预算偏好，系统会结合工具快照生成每日行程。',
    summaryTrip: '行程',
    summaryParty: '同行',
    summaryProtocol: '协议',
    unitDays: '天',
    unitPeople: '人',
    cardTitle: '行程需求',
    noCity: '未选择城市',

    sectionWhere: '目的地与日期',
    sectionParty: '同行与预算',
    sectionPrefs: '偏好设置',
    sectionExtra: '额外要求',

    labelCity: '目的地城市',
    placeholderCity: '例如: 北京',
    ruleCity: '请输入目的地城市',
    labelStartDate: '开始日期',
    ruleStartDate: '请选择开始日期',
    labelEndDate: '结束日期',
    ruleEndDate: '请选择结束日期',
    placeholderDate: '选择日期',

    labelAdults: '成人',
    labelChildren: '儿童',
    labelElders: '老人',
    labelCompanion: '同行类型',
    labelBudget: '总预算',
    placeholderBudget: '可不填',
    noOverspend: '不可超支',
    labelBudgetLevel: '预算档位',

    labelTransportation: '交通方式',
    labelAccommodation: '住宿偏好',
    labelPreferences: '旅行偏好',

    placeholderExtra: '请输入您的额外要求，例如：想去看升旗、需要无障碍设施、对海鲜过敏等...',

    submit: '开始规划行程',
    submitting: '正在生成中...',
    starting: '准备中...',
    done: '完成！',

    warnMaxDays: '旅行天数不能超过30天',
    warnDateOrder: '结束日期不能早于开始日期',
    errPickDate: '请选择日期',
    errPartySize: '同行人数至少为1人',
    successGenerated: '行程已生成！',
    errGenerate: '生成行程失败，请重试'
  },
  result: {
    back: '返回首页',
    edit: '编辑行程',
    save: '保存修改',
    cancel: '取消编辑',
    exportImage: '导出为图片',
    exportPdf: '导出为PDF',
    exportMenu: '导出行程',

    navOverview: '行程概览',
    navBudget: '预算明细',
    navMap: '全程地图',
    navDailyMaps: '每日地图',
    navDays: '每日行程',
    navWeather: '天气信息',
    day: '第{n}天',

    tripPlanTitle: '{city}旅行计划',
    dateLabel: '日期',
    dateRange: '{start} 至 {end}',
    overallSuggestions: '整体建议',

    budgetTitle: '预算明细',
    budgetAttractions: '景点门票',
    budgetHotels: '酒店住宿',
    budgetMeals: '餐饮费用',
    budgetTransportation: '交通费用',
    budgetTotal: '预估总费用',

    mapTitle: '全程地图',
    legendStay: '住宿',
    legendSights: '景点',
    legendFood: '餐饮',
    dailyMapsTitle: '每日地图',
    locationsCount: '{n} 个地点',
    noCoordinates: '暂无可展示坐标',

    dailyItinerary: '每日行程',
    descLabel: '行程描述',
    transportLabel: '交通方式',
    stayLabel: '住宿',
    attractionsSection: '景点安排',
    recommendedStay: '住宿推荐',
    mealsSection: '餐饮安排',

    addr: '地址',
    duration: '游览时长',
    durationMin: '{n}分钟',
    descField: '描述',
    rating: '评分',
    durationEditLabel: '游览时长(分钟):',
    addrEditLabel: '地址:',
    descEditLabel: '描述:',

    hotelType: '类型',
    hotelPriceRange: '价格范围',
    hotelDistance: '距离',

    weatherTitle: '天气信息',
    weatherDay: '白天',
    weatherNight: '夜间',

    mealBreakfast: '早餐',
    mealLunch: '午餐',
    mealDinner: '晚餐',
    mealSnack: '小吃',

    emptyTitle: '没有找到旅行计划数据',
    emptyDesc: '暂无旅行计划数据，请先创建行程',
    emptyAction: '返回首页创建行程',

    toastEditMode: '进入编辑模式',
    toastSaved: '修改已保存',
    toastCanceled: '已取消编辑',
    toastKeepOne: '每天至少需要保留一个景点',
    toastDeleted: '景点已删除',
    toastMapOk: '地图加载成功',
    toastMapFail: '地图加载失败',
    toastGenImage: '正在生成图片...',
    toastImageOk: '图片导出成功！',
    toastImageFail: '导出图片失败: {msg}',
    toastGenPdf: '正在生成PDF...',
    toastPdfOk: 'PDF导出成功！',
    toastPdfFail: '导出PDF失败: {msg}',
    errNoContent: '未找到内容元素',
    exportFilePrefix: '旅行计划',

    pointStay: '住宿',
    pointSights: '景点',
    pointFood: '餐饮',
    markerStay: '住',
    markerAttraction: '景{n}',
    markerBreakfast: '早',
    markerLunch: '午',
    markerDinner: '晚',
    markerSnack: '食',
    carriedOverHotel: '沿用前一晚住处，方便当天出发或取行李',
    visitMeta: '游览 {n} 分钟',
    mealCostMeta: '{label} | 约 ¥{cost}/人',
    infoAddr: '地址',
    infoMeta: '信息',
    infoDesc: '说明',
    infoDayType: '第{n}天 · {type}'
  }
}

const en: Messages = {
  app: {
    brand: 'HelloAgents Trip Planner',
    footer: 'HelloAgents Trip Planner ©2026',
    langLabel: 'Language'
  },
  home: {
    bannerTitle: 'Create an actionable travel plan',
    bannerSubtitle: 'Enter your destination, dates, party size, and budget preferences — the system builds a day-by-day itinerary from tool snapshots.',
    summaryTrip: 'Trip',
    summaryParty: 'Party',
    summaryProtocol: 'Protocol',
    unitDays: 'days',
    unitPeople: 'people',
    cardTitle: 'Trip Request',
    noCity: 'No city selected',

    sectionWhere: 'Destination & Dates',
    sectionParty: 'Party & Budget',
    sectionPrefs: 'Preferences',
    sectionExtra: 'Additional Notes',

    labelCity: 'Destination city',
    placeholderCity: 'e.g. Beijing',
    ruleCity: 'Please enter a destination city',
    labelStartDate: 'Start date',
    ruleStartDate: 'Please select a start date',
    labelEndDate: 'End date',
    ruleEndDate: 'Please select an end date',
    placeholderDate: 'Select date',

    labelAdults: 'Adults',
    labelChildren: 'Children',
    labelElders: 'Elders',
    labelCompanion: 'Companion type',
    labelBudget: 'Total budget',
    placeholderBudget: 'Optional',
    noOverspend: 'No overspend',
    labelBudgetLevel: 'Budget level',

    labelTransportation: 'Transportation',
    labelAccommodation: 'Accommodation',
    labelPreferences: 'Travel preferences',

    placeholderExtra: 'Add any extra requirements, e.g. watch the flag-raising ceremony, need accessible facilities, allergic to seafood...',

    submit: 'Start planning',
    submitting: 'Generating...',
    starting: 'Starting...',
    done: 'Done!',

    warnMaxDays: 'Trip length cannot exceed 30 days',
    warnDateOrder: 'End date cannot be earlier than start date',
    errPickDate: 'Please select dates',
    errPartySize: 'Party size must be at least 1',
    successGenerated: 'Trip plan generated!',
    errGenerate: 'Failed to generate trip plan, please retry'
  },
  result: {
    back: 'Back to home',
    edit: 'Edit itinerary',
    save: 'Save changes',
    cancel: 'Cancel',
    exportImage: 'Export as image',
    exportPdf: 'Export as PDF',
    exportMenu: 'Export',

    navOverview: 'Overview',
    navBudget: 'Budget',
    navMap: 'Full map',
    navDailyMaps: 'Daily maps',
    navDays: 'Daily itinerary',
    navWeather: 'Weather',
    day: 'Day {n}',

    tripPlanTitle: '{city} Trip Plan',
    dateLabel: 'Dates',
    dateRange: '{start} to {end}',
    overallSuggestions: 'Overall suggestions',

    budgetTitle: 'Budget',
    budgetAttractions: 'Attractions',
    budgetHotels: 'Hotels',
    budgetMeals: 'Meals',
    budgetTransportation: 'Transportation',
    budgetTotal: 'Estimated total',

    mapTitle: 'Full map',
    legendStay: 'Stay',
    legendSights: 'Sights',
    legendFood: 'Food',
    dailyMapsTitle: 'Daily maps',
    locationsCount: '{n} locations',
    noCoordinates: 'No coordinates to display',

    dailyItinerary: 'Daily itinerary',
    descLabel: 'Description',
    transportLabel: 'Transportation',
    stayLabel: 'Accommodation',
    attractionsSection: 'Attractions',
    recommendedStay: 'Recommended stay',
    mealsSection: 'Meals',

    addr: 'Address',
    duration: 'Duration',
    durationMin: '{n} min',
    descField: 'Description',
    rating: 'Rating',
    durationEditLabel: 'Duration (min):',
    addrEditLabel: 'Address:',
    descEditLabel: 'Description:',

    hotelType: 'Type',
    hotelPriceRange: 'Price range',
    hotelDistance: 'Distance',

    weatherTitle: 'Weather',
    weatherDay: 'Day',
    weatherNight: 'Night',

    mealBreakfast: 'Breakfast',
    mealLunch: 'Lunch',
    mealDinner: 'Dinner',
    mealSnack: 'Snack',

    emptyTitle: 'No trip plan found',
    emptyDesc: 'No trip plan data yet — create one first',
    emptyAction: 'Back to home to create a trip',

    toastEditMode: 'Edit mode enabled',
    toastSaved: 'Changes saved',
    toastCanceled: 'Edit canceled',
    toastKeepOne: 'Each day needs at least one attraction',
    toastDeleted: 'Attraction removed',
    toastMapOk: 'Map loaded',
    toastMapFail: 'Failed to load map',
    toastGenImage: 'Generating image...',
    toastImageOk: 'Image exported!',
    toastImageFail: 'Image export failed: {msg}',
    toastGenPdf: 'Generating PDF...',
    toastPdfOk: 'PDF exported!',
    toastPdfFail: 'PDF export failed: {msg}',
    errNoContent: 'Content element not found',
    exportFilePrefix: 'TripPlan',

    pointStay: 'Stay',
    pointSights: 'Sights',
    pointFood: 'Food',
    markerStay: 'H',
    markerAttraction: 'A{n}',
    markerBreakfast: 'B',
    markerLunch: 'L',
    markerDinner: 'D',
    markerSnack: 'S',
    carriedOverHotel: 'Same stay as the previous night for an easy start or luggage pickup',
    visitMeta: 'Visit {n} min',
    mealCostMeta: '{label} | ~¥{cost}/person',
    infoAddr: 'Address',
    infoMeta: 'Info',
    infoDesc: 'Notes',
    infoDayType: 'Day {n} · {type}'
  }
}

export const messages: Record<Locale, Messages> = { zh, en }
