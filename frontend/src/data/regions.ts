// All provincial-level regions of China and their prefecture-level cities.
// Generated once from Amap's /v3/config/district (subdistrict=2); English names
// are pinyin with conventional overrides (e.g. Hohhot, Urumqi, Kashgar, Taipei).
// `name` is the official Chinese name sent to the backend as TripRequest.city,
// because Amap does not resolve English city names ("Beijing" -> nationwide results).
// Municipalities, Hong Kong and Macau are a single city each.

export type RegionSupport = 'full' | 'noWeather' | 'unsupported'

export interface CityOption {
  /** Official Chinese name; this exact string is submitted as `city`. */
  name: string
  en: string
  adcode: string
  /**
   * Per-city exception to the province's support level. 怒江 is sent by its
   * short name: Amap place search mis-resolves the full name 怒江傈僳族自治州
   * (returns Beijing results), while the short name has no weather forecast.
   */
  support?: RegionSupport
}

export interface ProvinceOption {
  name: string
  en: string
  adcode: string
  /** Amap coverage: Hong Kong/Macau have POIs but no weather; Taiwan cannot be searched by city name. */
  support: RegionSupport
  cities: CityOption[]
}

export const PROVINCES: ProvinceOption[] = [
  {
    name: "北京市",
    en: "Beijing",
    adcode: '110000',
    support: 'full',
    cities: [
      { name: "北京市", en: "Beijing", adcode: '110000' }
    ]
  },
  {
    name: "天津市",
    en: "Tianjin",
    adcode: '120000',
    support: 'full',
    cities: [
      { name: "天津市", en: "Tianjin", adcode: '120000' }
    ]
  },
  {
    name: "河北省",
    en: "Hebei",
    adcode: '130000',
    support: 'full',
    cities: [
      { name: "石家庄市", en: "Shijiazhuang", adcode: '130100' },
      { name: "唐山市", en: "Tangshan", adcode: '130200' },
      { name: "秦皇岛市", en: "Qinhuangdao", adcode: '130300' },
      { name: "邯郸市", en: "Handan", adcode: '130400' },
      { name: "邢台市", en: "Xingtai", adcode: '130500' },
      { name: "保定市", en: "Baoding", adcode: '130600' },
      { name: "张家口市", en: "Zhangjiakou", adcode: '130700' },
      { name: "承德市", en: "Chengde", adcode: '130800' },
      { name: "沧州市", en: "Cangzhou", adcode: '130900' },
      { name: "廊坊市", en: "Langfang", adcode: '131000' },
      { name: "衡水市", en: "Hengshui", adcode: '131100' }
    ]
  },
  {
    name: "山西省",
    en: "Shanxi",
    adcode: '140000',
    support: 'full',
    cities: [
      { name: "太原市", en: "Taiyuan", adcode: '140100' },
      { name: "大同市", en: "Datong", adcode: '140200' },
      { name: "阳泉市", en: "Yangquan", adcode: '140300' },
      { name: "长治市", en: "Changzhi", adcode: '140400' },
      { name: "晋城市", en: "Jincheng", adcode: '140500' },
      { name: "朔州市", en: "Shuozhou", adcode: '140600' },
      { name: "晋中市", en: "Jinzhong", adcode: '140700' },
      { name: "运城市", en: "Yuncheng", adcode: '140800' },
      { name: "忻州市", en: "Xinzhou", adcode: '140900' },
      { name: "临汾市", en: "Linfen", adcode: '141000' },
      { name: "吕梁市", en: "Lüliang", adcode: '141100' }
    ]
  },
  {
    name: "内蒙古自治区",
    en: "Inner Mongolia",
    adcode: '150000',
    support: 'full',
    cities: [
      { name: "呼和浩特市", en: "Hohhot", adcode: '150100' },
      { name: "包头市", en: "Baotou", adcode: '150200' },
      { name: "乌海市", en: "Wuhai", adcode: '150300' },
      { name: "赤峰市", en: "Chifeng", adcode: '150400' },
      { name: "通辽市", en: "Tongliao", adcode: '150500' },
      { name: "鄂尔多斯市", en: "Ordos", adcode: '150600' },
      { name: "呼伦贝尔市", en: "Hulunbuir", adcode: '150700' },
      { name: "巴彦淖尔市", en: "Bayannur", adcode: '150800' },
      { name: "乌兰察布市", en: "Ulanqab", adcode: '150900' },
      { name: "兴安盟", en: "Hinggan", adcode: '152200' },
      { name: "锡林郭勒盟", en: "Xilingol", adcode: '152500' },
      { name: "阿拉善盟", en: "Alxa", adcode: '152900' }
    ]
  },
  {
    name: "辽宁省",
    en: "Liaoning",
    adcode: '210000',
    support: 'full',
    cities: [
      { name: "沈阳市", en: "Shenyang", adcode: '210100' },
      { name: "大连市", en: "Dalian", adcode: '210200' },
      { name: "鞍山市", en: "Anshan", adcode: '210300' },
      { name: "抚顺市", en: "Fushun", adcode: '210400' },
      { name: "本溪市", en: "Benxi", adcode: '210500' },
      { name: "丹东市", en: "Dandong", adcode: '210600' },
      { name: "锦州市", en: "Jinzhou", adcode: '210700' },
      { name: "营口市", en: "Yingkou", adcode: '210800' },
      { name: "阜新市", en: "Fuxin", adcode: '210900' },
      { name: "辽阳市", en: "Liaoyang", adcode: '211000' },
      { name: "盘锦市", en: "Panjin", adcode: '211100' },
      { name: "铁岭市", en: "Tieling", adcode: '211200' },
      { name: "朝阳市", en: "Chaoyang", adcode: '211300' },
      { name: "葫芦岛市", en: "Huludao", adcode: '211400' }
    ]
  },
  {
    name: "吉林省",
    en: "Jilin",
    adcode: '220000',
    support: 'full',
    cities: [
      { name: "长春市", en: "Changchun", adcode: '220100' },
      { name: "吉林市", en: "Jilin", adcode: '220200' },
      { name: "四平市", en: "Siping", adcode: '220300' },
      { name: "辽源市", en: "Liaoyuan", adcode: '220400' },
      { name: "通化市", en: "Tonghua", adcode: '220500' },
      { name: "白山市", en: "Baishan", adcode: '220600' },
      { name: "松原市", en: "Songyuan", adcode: '220700' },
      { name: "白城市", en: "Baicheng", adcode: '220800' },
      { name: "延边朝鲜族自治州", en: "Yanbian", adcode: '222400' }
    ]
  },
  {
    name: "黑龙江省",
    en: "Heilongjiang",
    adcode: '230000',
    support: 'full',
    cities: [
      { name: "哈尔滨市", en: "Harbin", adcode: '230100' },
      { name: "齐齐哈尔市", en: "Qiqihar", adcode: '230200' },
      { name: "鸡西市", en: "Jixi", adcode: '230300' },
      { name: "鹤岗市", en: "Hegang", adcode: '230400' },
      { name: "双鸭山市", en: "Shuangyashan", adcode: '230500' },
      { name: "大庆市", en: "Daqing", adcode: '230600' },
      { name: "伊春市", en: "Yichun", adcode: '230700' },
      { name: "佳木斯市", en: "Jiamusi", adcode: '230800' },
      { name: "七台河市", en: "Qitaihe", adcode: '230900' },
      { name: "牡丹江市", en: "Mudanjiang", adcode: '231000' },
      { name: "黑河市", en: "Heihe", adcode: '231100' },
      { name: "绥化市", en: "Suihua", adcode: '231200' },
      { name: "大兴安岭地区", en: "Da Hinggan Ling", adcode: '232700' }
    ]
  },
  {
    name: "上海市",
    en: "Shanghai",
    adcode: '310000',
    support: 'full',
    cities: [
      { name: "上海市", en: "Shanghai", adcode: '310000' }
    ]
  },
  {
    name: "江苏省",
    en: "Jiangsu",
    adcode: '320000',
    support: 'full',
    cities: [
      { name: "南京市", en: "Nanjing", adcode: '320100' },
      { name: "无锡市", en: "Wuxi", adcode: '320200' },
      { name: "徐州市", en: "Xuzhou", adcode: '320300' },
      { name: "常州市", en: "Changzhou", adcode: '320400' },
      { name: "苏州市", en: "Suzhou", adcode: '320500' },
      { name: "南通市", en: "Nantong", adcode: '320600' },
      { name: "连云港市", en: "Lianyungang", adcode: '320700' },
      { name: "淮安市", en: "Huai'an", adcode: '320800' },
      { name: "盐城市", en: "Yancheng", adcode: '320900' },
      { name: "扬州市", en: "Yangzhou", adcode: '321000' },
      { name: "镇江市", en: "Zhenjiang", adcode: '321100' },
      { name: "泰州市", en: "Taizhou", adcode: '321200' },
      { name: "宿迁市", en: "Suqian", adcode: '321300' }
    ]
  },
  {
    name: "浙江省",
    en: "Zhejiang",
    adcode: '330000',
    support: 'full',
    cities: [
      { name: "杭州市", en: "Hangzhou", adcode: '330100' },
      { name: "宁波市", en: "Ningbo", adcode: '330200' },
      { name: "温州市", en: "Wenzhou", adcode: '330300' },
      { name: "嘉兴市", en: "Jiaxing", adcode: '330400' },
      { name: "湖州市", en: "Huzhou", adcode: '330500' },
      { name: "绍兴市", en: "Shaoxing", adcode: '330600' },
      { name: "金华市", en: "Jinhua", adcode: '330700' },
      { name: "衢州市", en: "Quzhou", adcode: '330800' },
      { name: "舟山市", en: "Zhoushan", adcode: '330900' },
      { name: "台州市", en: "Taizhou", adcode: '331000' },
      { name: "丽水市", en: "Lishui", adcode: '331100' }
    ]
  },
  {
    name: "安徽省",
    en: "Anhui",
    adcode: '340000',
    support: 'full',
    cities: [
      { name: "合肥市", en: "Hefei", adcode: '340100' },
      { name: "芜湖市", en: "Wuhu", adcode: '340200' },
      { name: "蚌埠市", en: "Bengbu", adcode: '340300' },
      { name: "淮南市", en: "Huainan", adcode: '340400' },
      { name: "马鞍山市", en: "Ma'anshan", adcode: '340500' },
      { name: "淮北市", en: "Huaibei", adcode: '340600' },
      { name: "铜陵市", en: "Tongling", adcode: '340700' },
      { name: "安庆市", en: "Anqing", adcode: '340800' },
      { name: "黄山市", en: "Huangshan", adcode: '341000' },
      { name: "滁州市", en: "Chuzhou", adcode: '341100' },
      { name: "阜阳市", en: "Fuyang", adcode: '341200' },
      { name: "宿州市", en: "Suzhou (Anhui)", adcode: '341300' },
      { name: "六安市", en: "Lu'an", adcode: '341500' },
      { name: "亳州市", en: "Bozhou", adcode: '341600' },
      { name: "池州市", en: "Chizhou", adcode: '341700' },
      { name: "宣城市", en: "Xuancheng", adcode: '341800' }
    ]
  },
  {
    name: "福建省",
    en: "Fujian",
    adcode: '350000',
    support: 'full',
    cities: [
      { name: "福州市", en: "Fuzhou", adcode: '350100' },
      { name: "厦门市", en: "Xiamen", adcode: '350200' },
      { name: "莆田市", en: "Putian", adcode: '350300' },
      { name: "三明市", en: "Sanming", adcode: '350400' },
      { name: "泉州市", en: "Quanzhou", adcode: '350500' },
      { name: "漳州市", en: "Zhangzhou", adcode: '350600' },
      { name: "南平市", en: "Nanping", adcode: '350700' },
      { name: "龙岩市", en: "Longyan", adcode: '350800' },
      { name: "宁德市", en: "Ningde", adcode: '350900' }
    ]
  },
  {
    name: "江西省",
    en: "Jiangxi",
    adcode: '360000',
    support: 'full',
    cities: [
      { name: "南昌市", en: "Nanchang", adcode: '360100' },
      { name: "景德镇市", en: "Jingdezhen", adcode: '360200' },
      { name: "萍乡市", en: "Pingxiang", adcode: '360300' },
      { name: "九江市", en: "Jiujiang", adcode: '360400' },
      { name: "新余市", en: "Xinyu", adcode: '360500' },
      { name: "鹰潭市", en: "Yingtan", adcode: '360600' },
      { name: "赣州市", en: "Ganzhou", adcode: '360700' },
      { name: "吉安市", en: "Ji'an", adcode: '360800' },
      { name: "宜春市", en: "Yichun", adcode: '360900' },
      { name: "抚州市", en: "Fuzhou", adcode: '361000' },
      { name: "上饶市", en: "Shangrao", adcode: '361100' }
    ]
  },
  {
    name: "山东省",
    en: "Shandong",
    adcode: '370000',
    support: 'full',
    cities: [
      { name: "济南市", en: "Jinan", adcode: '370100' },
      { name: "青岛市", en: "Qingdao", adcode: '370200' },
      { name: "淄博市", en: "Zibo", adcode: '370300' },
      { name: "枣庄市", en: "Zaozhuang", adcode: '370400' },
      { name: "东营市", en: "Dongying", adcode: '370500' },
      { name: "烟台市", en: "Yantai", adcode: '370600' },
      { name: "潍坊市", en: "Weifang", adcode: '370700' },
      { name: "济宁市", en: "Jining", adcode: '370800' },
      { name: "泰安市", en: "Tai'an", adcode: '370900' },
      { name: "威海市", en: "Weihai", adcode: '371000' },
      { name: "日照市", en: "Rizhao", adcode: '371100' },
      { name: "临沂市", en: "Linyi", adcode: '371300' },
      { name: "德州市", en: "Dezhou", adcode: '371400' },
      { name: "聊城市", en: "Liaocheng", adcode: '371500' },
      { name: "滨州市", en: "Binzhou", adcode: '371600' },
      { name: "菏泽市", en: "Heze", adcode: '371700' }
    ]
  },
  {
    name: "河南省",
    en: "Henan",
    adcode: '410000',
    support: 'full',
    cities: [
      { name: "郑州市", en: "Zhengzhou", adcode: '410100' },
      { name: "开封市", en: "Kaifeng", adcode: '410200' },
      { name: "洛阳市", en: "Luoyang", adcode: '410300' },
      { name: "平顶山市", en: "Pingdingshan", adcode: '410400' },
      { name: "安阳市", en: "Anyang", adcode: '410500' },
      { name: "鹤壁市", en: "Hebi", adcode: '410600' },
      { name: "新乡市", en: "Xinxiang", adcode: '410700' },
      { name: "焦作市", en: "Jiaozuo", adcode: '410800' },
      { name: "濮阳市", en: "Puyang", adcode: '410900' },
      { name: "许昌市", en: "Xuchang", adcode: '411000' },
      { name: "漯河市", en: "Luohe", adcode: '411100' },
      { name: "三门峡市", en: "Sanmenxia", adcode: '411200' },
      { name: "南阳市", en: "Nanyang", adcode: '411300' },
      { name: "商丘市", en: "Shangqiu", adcode: '411400' },
      { name: "信阳市", en: "Xinyang", adcode: '411500' },
      { name: "周口市", en: "Zhoukou", adcode: '411600' },
      { name: "驻马店市", en: "Zhumadian", adcode: '411700' },
      { name: "济源市", en: "Jiyuan", adcode: '419001' }
    ]
  },
  {
    name: "湖北省",
    en: "Hubei",
    adcode: '420000',
    support: 'full',
    cities: [
      { name: "武汉市", en: "Wuhan", adcode: '420100' },
      { name: "黄石市", en: "Huangshi", adcode: '420200' },
      { name: "十堰市", en: "Shiyan", adcode: '420300' },
      { name: "宜昌市", en: "Yichang", adcode: '420500' },
      { name: "襄阳市", en: "Xiangyang", adcode: '420600' },
      { name: "鄂州市", en: "Ezhou", adcode: '420700' },
      { name: "荆门市", en: "Jingmen", adcode: '420800' },
      { name: "孝感市", en: "Xiaogan", adcode: '420900' },
      { name: "荆州市", en: "Jingzhou", adcode: '421000' },
      { name: "黄冈市", en: "Huanggang", adcode: '421100' },
      { name: "咸宁市", en: "Xianning", adcode: '421200' },
      { name: "随州市", en: "Suizhou", adcode: '421300' },
      { name: "恩施土家族苗族自治州", en: "Enshi", adcode: '422800' },
      { name: "仙桃市", en: "Xiantao", adcode: '429004' },
      { name: "潜江市", en: "Qianjiang", adcode: '429005' },
      { name: "天门市", en: "Tianmen", adcode: '429006' },
      { name: "神农架林区", en: "Shennongjia", adcode: '429021' }
    ]
  },
  {
    name: "湖南省",
    en: "Hunan",
    adcode: '430000',
    support: 'full',
    cities: [
      { name: "长沙市", en: "Changsha", adcode: '430100' },
      { name: "株洲市", en: "Zhuzhou", adcode: '430200' },
      { name: "湘潭市", en: "Xiangtan", adcode: '430300' },
      { name: "衡阳市", en: "Hengyang", adcode: '430400' },
      { name: "邵阳市", en: "Shaoyang", adcode: '430500' },
      { name: "岳阳市", en: "Yueyang", adcode: '430600' },
      { name: "常德市", en: "Changde", adcode: '430700' },
      { name: "张家界市", en: "Zhangjiajie", adcode: '430800' },
      { name: "益阳市", en: "Yiyang", adcode: '430900' },
      { name: "郴州市", en: "Chenzhou", adcode: '431000' },
      { name: "永州市", en: "Yongzhou", adcode: '431100' },
      { name: "怀化市", en: "Huaihua", adcode: '431200' },
      { name: "娄底市", en: "Loudi", adcode: '431300' },
      { name: "湘西土家族苗族自治州", en: "Xiangxi", adcode: '433100' }
    ]
  },
  {
    name: "广东省",
    en: "Guangdong",
    adcode: '440000',
    support: 'full',
    cities: [
      { name: "广州市", en: "Guangzhou", adcode: '440100' },
      { name: "韶关市", en: "Shaoguan", adcode: '440200' },
      { name: "深圳市", en: "Shenzhen", adcode: '440300' },
      { name: "珠海市", en: "Zhuhai", adcode: '440400' },
      { name: "汕头市", en: "Shantou", adcode: '440500' },
      { name: "佛山市", en: "Foshan", adcode: '440600' },
      { name: "江门市", en: "Jiangmen", adcode: '440700' },
      { name: "湛江市", en: "Zhanjiang", adcode: '440800' },
      { name: "茂名市", en: "Maoming", adcode: '440900' },
      { name: "肇庆市", en: "Zhaoqing", adcode: '441200' },
      { name: "惠州市", en: "Huizhou", adcode: '441300' },
      { name: "梅州市", en: "Meizhou", adcode: '441400' },
      { name: "汕尾市", en: "Shanwei", adcode: '441500' },
      { name: "河源市", en: "Heyuan", adcode: '441600' },
      { name: "阳江市", en: "Yangjiang", adcode: '441700' },
      { name: "清远市", en: "Qingyuan", adcode: '441800' },
      { name: "东莞市", en: "Dongguan", adcode: '441900' },
      { name: "中山市", en: "Zhongshan", adcode: '442000' },
      { name: "潮州市", en: "Chaozhou", adcode: '445100' },
      { name: "揭阳市", en: "Jieyang", adcode: '445200' },
      { name: "云浮市", en: "Yunfu", adcode: '445300' }
    ]
  },
  {
    name: "广西壮族自治区",
    en: "Guangxi",
    adcode: '450000',
    support: 'full',
    cities: [
      { name: "南宁市", en: "Nanning", adcode: '450100' },
      { name: "柳州市", en: "Liuzhou", adcode: '450200' },
      { name: "桂林市", en: "Guilin", adcode: '450300' },
      { name: "梧州市", en: "Wuzhou", adcode: '450400' },
      { name: "北海市", en: "Beihai", adcode: '450500' },
      { name: "防城港市", en: "Fangchenggang", adcode: '450600' },
      { name: "钦州市", en: "Qinzhou", adcode: '450700' },
      { name: "贵港市", en: "Guigang", adcode: '450800' },
      { name: "玉林市", en: "Yulin", adcode: '450900' },
      { name: "百色市", en: "Baise", adcode: '451000' },
      { name: "贺州市", en: "Hezhou", adcode: '451100' },
      { name: "河池市", en: "Hechi", adcode: '451200' },
      { name: "来宾市", en: "Laibin", adcode: '451300' },
      { name: "崇左市", en: "Chongzuo", adcode: '451400' }
    ]
  },
  {
    name: "海南省",
    en: "Hainan",
    adcode: '460000',
    support: 'full',
    cities: [
      { name: "海口市", en: "Haikou", adcode: '460100' },
      { name: "三亚市", en: "Sanya", adcode: '460200' },
      { name: "三沙市", en: "Sansha", adcode: '460300' },
      { name: "儋州市", en: "Danzhou", adcode: '460400' },
      { name: "五指山市", en: "Wuzhishan", adcode: '469001' },
      { name: "琼海市", en: "Qionghai", adcode: '469002' },
      { name: "文昌市", en: "Wenchang", adcode: '469005' },
      { name: "万宁市", en: "Wanning", adcode: '469006' },
      { name: "东方市", en: "Dongfang", adcode: '469007' },
      { name: "定安县", en: "Ding'an County", adcode: '469021' },
      { name: "屯昌县", en: "Tunchang County", adcode: '469022' },
      { name: "澄迈县", en: "Chengmai County", adcode: '469023' },
      { name: "临高县", en: "Lingao County", adcode: '469024' },
      { name: "白沙黎族自治县", en: "Baisha County", adcode: '469025' },
      { name: "昌江黎族自治县", en: "Changjiang County", adcode: '469026' },
      { name: "乐东黎族自治县", en: "Ledong County", adcode: '469027' },
      { name: "陵水黎族自治县", en: "Lingshui County", adcode: '469028' },
      { name: "保亭黎族苗族自治县", en: "Baoting County", adcode: '469029' },
      { name: "琼中黎族苗族自治县", en: "Qiongzhong County", adcode: '469030' }
    ]
  },
  {
    name: "重庆市",
    en: "Chongqing",
    adcode: '500000',
    support: 'full',
    cities: [
      { name: "重庆市", en: "Chongqing", adcode: '500000' }
    ]
  },
  {
    name: "四川省",
    en: "Sichuan",
    adcode: '510000',
    support: 'full',
    cities: [
      { name: "成都市", en: "Chengdu", adcode: '510100' },
      { name: "自贡市", en: "Zigong", adcode: '510300' },
      { name: "攀枝花市", en: "Panzhihua", adcode: '510400' },
      { name: "泸州市", en: "Luzhou", adcode: '510500' },
      { name: "德阳市", en: "Deyang", adcode: '510600' },
      { name: "绵阳市", en: "Mianyang", adcode: '510700' },
      { name: "广元市", en: "Guangyuan", adcode: '510800' },
      { name: "遂宁市", en: "Suining", adcode: '510900' },
      { name: "内江市", en: "Neijiang", adcode: '511000' },
      { name: "乐山市", en: "Leshan", adcode: '511100' },
      { name: "南充市", en: "Nanchong", adcode: '511300' },
      { name: "眉山市", en: "Meishan", adcode: '511400' },
      { name: "宜宾市", en: "Yibin", adcode: '511500' },
      { name: "广安市", en: "Guang'an", adcode: '511600' },
      { name: "达州市", en: "Dazhou", adcode: '511700' },
      { name: "雅安市", en: "Ya'an", adcode: '511800' },
      { name: "巴中市", en: "Bazhong", adcode: '511900' },
      { name: "资阳市", en: "Ziyang", adcode: '512000' },
      { name: "阿坝藏族羌族自治州", en: "Ngawa", adcode: '513200' },
      { name: "甘孜藏族自治州", en: "Garze", adcode: '513300' },
      { name: "凉山彝族自治州", en: "Liangshan", adcode: '513400' }
    ]
  },
  {
    name: "贵州省",
    en: "Guizhou",
    adcode: '520000',
    support: 'full',
    cities: [
      { name: "贵阳市", en: "Guiyang", adcode: '520100' },
      { name: "六盘水市", en: "Liupanshui", adcode: '520200' },
      { name: "遵义市", en: "Zunyi", adcode: '520300' },
      { name: "安顺市", en: "Anshun", adcode: '520400' },
      { name: "毕节市", en: "Bijie", adcode: '520500' },
      { name: "铜仁市", en: "Tongren", adcode: '520600' },
      { name: "黔西南布依族苗族自治州", en: "Qianxinan", adcode: '522300' },
      { name: "黔东南苗族侗族自治州", en: "Qiandongnan", adcode: '522600' },
      { name: "黔南布依族苗族自治州", en: "Qiannan", adcode: '522700' }
    ]
  },
  {
    name: "云南省",
    en: "Yunnan",
    adcode: '530000',
    support: 'full',
    cities: [
      { name: "昆明市", en: "Kunming", adcode: '530100' },
      { name: "曲靖市", en: "Qujing", adcode: '530300' },
      { name: "玉溪市", en: "Yuxi", adcode: '530400' },
      { name: "保山市", en: "Baoshan", adcode: '530500' },
      { name: "昭通市", en: "Zhaotong", adcode: '530600' },
      { name: "丽江市", en: "Lijiang", adcode: '530700' },
      { name: "普洱市", en: "Pu'er", adcode: '530800' },
      { name: "临沧市", en: "Lincang", adcode: '530900' },
      { name: "楚雄彝族自治州", en: "Chuxiong", adcode: '532300' },
      { name: "红河哈尼族彝族自治州", en: "Honghe", adcode: '532500' },
      { name: "文山壮族苗族自治州", en: "Wenshan", adcode: '532600' },
      { name: "西双版纳傣族自治州", en: "Xishuangbanna", adcode: '532800' },
      { name: "大理白族自治州", en: "Dali", adcode: '532900' },
      { name: "德宏傣族景颇族自治州", en: "Dehong", adcode: '533100' },
      { name: "怒江", en: "Nujiang", adcode: '533300', support: 'noWeather' },
      { name: "迪庆藏族自治州", en: "Dêqên (Diqing)", adcode: '533400' }
    ]
  },
  {
    name: "西藏自治区",
    en: "Tibet",
    adcode: '540000',
    support: 'full',
    cities: [
      { name: "拉萨市", en: "Lhasa", adcode: '540100' },
      { name: "日喀则市", en: "Shigatse", adcode: '540200' },
      { name: "昌都市", en: "Qamdo", adcode: '540300' },
      { name: "林芝市", en: "Nyingchi", adcode: '540400' },
      { name: "山南市", en: "Shannan", adcode: '540500' },
      { name: "那曲市", en: "Nagqu", adcode: '540600' },
      { name: "阿里地区", en: "Ngari", adcode: '542500' }
    ]
  },
  {
    name: "陕西省",
    en: "Shaanxi",
    adcode: '610000',
    support: 'full',
    cities: [
      { name: "西安市", en: "Xi'an", adcode: '610100' },
      { name: "铜川市", en: "Tongchuan", adcode: '610200' },
      { name: "宝鸡市", en: "Baoji", adcode: '610300' },
      { name: "咸阳市", en: "Xianyang", adcode: '610400' },
      { name: "渭南市", en: "Weinan", adcode: '610500' },
      { name: "延安市", en: "Yan'an", adcode: '610600' },
      { name: "汉中市", en: "Hanzhong", adcode: '610700' },
      { name: "榆林市", en: "Yulin", adcode: '610800' },
      { name: "安康市", en: "Ankang", adcode: '610900' },
      { name: "商洛市", en: "Shangluo", adcode: '611000' }
    ]
  },
  {
    name: "甘肃省",
    en: "Gansu",
    adcode: '620000',
    support: 'full',
    cities: [
      { name: "兰州市", en: "Lanzhou", adcode: '620100' },
      { name: "嘉峪关市", en: "Jiayuguan", adcode: '620200' },
      { name: "金昌市", en: "Jinchang", adcode: '620300' },
      { name: "白银市", en: "Baiyin", adcode: '620400' },
      { name: "天水市", en: "Tianshui", adcode: '620500' },
      { name: "武威市", en: "Wuwei", adcode: '620600' },
      { name: "张掖市", en: "Zhangye", adcode: '620700' },
      { name: "平凉市", en: "Pingliang", adcode: '620800' },
      { name: "酒泉市", en: "Jiuquan", adcode: '620900' },
      { name: "庆阳市", en: "Qingyang", adcode: '621000' },
      { name: "定西市", en: "Dingxi", adcode: '621100' },
      { name: "陇南市", en: "Longnan", adcode: '621200' },
      { name: "临夏回族自治州", en: "Linxia", adcode: '622900' },
      { name: "甘南藏族自治州", en: "Gannan", adcode: '623000' }
    ]
  },
  {
    name: "青海省",
    en: "Qinghai",
    adcode: '630000',
    support: 'full',
    cities: [
      { name: "西宁市", en: "Xining", adcode: '630100' },
      { name: "海东市", en: "Haidong", adcode: '630200' },
      { name: "海北藏族自治州", en: "Haibei", adcode: '632200' },
      { name: "黄南藏族自治州", en: "Huangnan", adcode: '632300' },
      { name: "海南藏族自治州", en: "Hainan (Qinghai)", adcode: '632500' },
      { name: "果洛藏族自治州", en: "Golog", adcode: '632600' },
      { name: "玉树藏族自治州", en: "Yushu", adcode: '632700' },
      { name: "海西蒙古族藏族自治州", en: "Haixi", adcode: '632800' }
    ]
  },
  {
    name: "宁夏回族自治区",
    en: "Ningxia",
    adcode: '640000',
    support: 'full',
    cities: [
      { name: "银川市", en: "Yinchuan", adcode: '640100' },
      { name: "石嘴山市", en: "Shizuishan", adcode: '640200' },
      { name: "吴忠市", en: "Wuzhong", adcode: '640300' },
      { name: "固原市", en: "Guyuan", adcode: '640400' },
      { name: "中卫市", en: "Zhongwei", adcode: '640500' }
    ]
  },
  {
    name: "新疆维吾尔自治区",
    en: "Xinjiang",
    adcode: '650000',
    support: 'full',
    cities: [
      { name: "乌鲁木齐市", en: "Urumqi", adcode: '650100' },
      { name: "克拉玛依市", en: "Karamay", adcode: '650200' },
      { name: "吐鲁番市", en: "Turpan", adcode: '650400' },
      { name: "哈密市", en: "Hami", adcode: '650500' },
      { name: "昌吉回族自治州", en: "Changji", adcode: '652300' },
      { name: "博尔塔拉蒙古自治州", en: "Bortala", adcode: '652700' },
      { name: "巴音郭楞蒙古自治州", en: "Bayingolin", adcode: '652800' },
      { name: "阿克苏地区", en: "Aksu", adcode: '652900' },
      { name: "克孜勒苏柯尔克孜自治州", en: "Kizilsu", adcode: '653000' },
      { name: "喀什地区", en: "Kashgar", adcode: '653100' },
      { name: "和田地区", en: "Hotan", adcode: '653200' },
      { name: "伊犁哈萨克自治州", en: "Ili", adcode: '654000' },
      { name: "塔城地区", en: "Tacheng", adcode: '654200' },
      { name: "阿勒泰地区", en: "Altay", adcode: '654300' },
      { name: "石河子市", en: "Shihezi", adcode: '659001' },
      { name: "阿拉尔市", en: "Aral", adcode: '659002' },
      { name: "图木舒克市", en: "Tumxuk", adcode: '659003' },
      { name: "五家渠市", en: "Wujiaqu", adcode: '659004' },
      { name: "北屯市", en: "Beitun", adcode: '659005' },
      { name: "铁门关市", en: "Tiemenguan", adcode: '659006' },
      { name: "双河市", en: "Shuanghe", adcode: '659007' },
      { name: "可克达拉市", en: "Kokdala", adcode: '659008' },
      { name: "昆玉市", en: "Kunyu", adcode: '659009' },
      { name: "胡杨河市", en: "Huyanghe", adcode: '659010' },
      { name: "新星市", en: "Xinxing", adcode: '659011' },
      { name: "白杨市", en: "Baiyang", adcode: '659012' }
    ]
  },
  {
    name: "台湾省",
    en: "Taiwan",
    adcode: '710000',
    support: 'unsupported',
    cities: [
      { name: "台北市", en: "Taipei", adcode: '710100' },
      { name: "高雄市", en: "Kaohsiung", adcode: '710200' },
      { name: "新北市", en: "New Taipei", adcode: '710300' },
      { name: "台中市", en: "Taichung", adcode: '710400' },
      { name: "台南市", en: "Tainan", adcode: '710500' },
      { name: "桃园市", en: "Taoyuan", adcode: '710600' },
      { name: "新竹县", en: "Hsinchu County", adcode: '710700' },
      { name: "屏东县", en: "Pingtung", adcode: '710800' },
      { name: "南投县", en: "Nantou", adcode: '710900' },
      { name: "花莲县", en: "Hualien", adcode: '711000' },
      { name: "苗栗县", en: "Miaoli", adcode: '711100' },
      { name: "新竹市", en: "Hsinchu City", adcode: '711200' },
      { name: "彰化县", en: "Changhua", adcode: '711300' },
      { name: "云林县", en: "Yunlin", adcode: '711400' },
      { name: "台东县", en: "Taitung", adcode: '711500' },
      { name: "基隆市", en: "Keelung", adcode: '711600' },
      { name: "宜兰县", en: "Yilan", adcode: '711700' },
      { name: "嘉义市", en: "Chiayi City", adcode: '711800' },
      { name: "嘉义县", en: "Chiayi County", adcode: '711900' },
      { name: "澎湖县", en: "Penghu", adcode: '712000' }
    ]
  },
  {
    name: "香港特别行政区",
    en: "Hong Kong",
    adcode: '810000',
    support: 'noWeather',
    cities: [
      { name: "香港", en: "Hong Kong", adcode: '810000' }
    ]
  },
  {
    name: "澳门特别行政区",
    en: "Macau",
    adcode: '820000',
    support: 'noWeather',
    cities: [
      { name: "澳门", en: "Macau", adcode: '820000' }
    ]
  }
]

const SUFFIX = /(特别行政区|市|地区|盟|林区)$/
const short = (value: string) => value.trim().replace(SUFFIX, '')

/** Find the province/city for a saved city string (full or short Chinese name, or English). */
/** Effective coverage of a city: its own override, else its province's. */
export const citySupport = (province: ProvinceOption, city: CityOption): RegionSupport => city.support ?? province.support

export function findCity(value: string | null | undefined): { province: ProvinceOption; city: CityOption } | null {
  const raw = String(value ?? '').trim()
  if (!raw) return null
  const lower = raw.toLowerCase()
  for (const province of PROVINCES) {
    for (const city of province.cities) {
      if (city.name === raw || short(city.name) === short(raw) || city.en.toLowerCase() === lower) {
        return { province, city }
      }
    }
  }
  return null
}
