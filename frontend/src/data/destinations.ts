// Destination photography for the home-page carousel and the /credits page.
// Migrated from the A2 design review (out/ui-design-review-20261111). Source,
// credit and license strings are kept verbatim, including resize/edit notes.
// Do not replace these with random or AI-generated images.

export interface Destination {
  id: string
  region?: string
  province: string
  city: string
  landmark: string
  title: string
  description: string
  en: { province: string; city: string; title: string; description: string }
  image: string
  /** CSS object-position used to crop the photo inside the screen. */
  objectPosition?: string
  /** Original photo page. */
  source: string
  /** Author / platform, plus any resize or edit note. */
  credit: string
  /** License name, URL, and any resize/edit note. */
  license: string
}

const images = import.meta.glob<string>('../assets/destinations/*.jpg', {
  eager: true,
  query: '?url',
  import: 'default'
})

const imageFor = (id: string): string => {
  const url = images[`../assets/destinations/${id}.jpg`]
  if (!url) throw new Error(`Missing destination image: ${id}`)
  return url
}

export const DESTINATIONS: Destination[] = [
  {
    "id": "region-east",
    "image": imageFor("region-east"),
    "region": "华东",
    "province": "上海市",
    "city": "上海",
    "landmark": "外滩",
    "title": "外滩",
    "description": "把江风与城市天际线，放进下一段旅程的想象。",
    "en": {
      "province": "Shanghai",
      "city": "Shanghai",
      "title": "The Bund",
      "description": "Carry the river breeze and the skyline into your next trip."
    },
    "source": "https://unsplash.com/photos/orient-pearl-shanghai-china-taken-during-daytime-uKyzXEc2k_s",
    "credit": "Edward He (@bingham008) / Unsplash",
    "license": "Unsplash License — https://unsplash.com/license；下载为1100px宽JPEG"
  },
  {
    "id": "region-north",
    "image": imageFor("region-north"),
    "region": "华北",
    "province": "北京市",
    "city": "北京",
    "landmark": "长城",
    "title": "长城",
    "description": "循着山脊间延展的城墙，寻找属于自己的远行视角。",
    "en": {
      "province": "Beijing",
      "city": "Beijing",
      "title": "The Great Wall",
      "description": "Follow the wall along the ridgeline and find your own view of the journey."
    },
    "objectPosition": "50% 70%",
    "source": "https://unsplash.com/photos/people-walking-up-the-great-wall-of-china-HGy0zlJVpS8",
    "credit": "ran liwen (@nikol_royce) / Unsplash",
    "license": "Unsplash License — https://unsplash.com/license；下载为1100px宽JPEG"
  },
  {
    "id": "region-northwest",
    "image": imageFor("region-northwest"),
    "region": "西北",
    "province": "甘肃省",
    "city": "敦煌",
    "landmark": "鸣沙山月牙泉",
    "title": "鸣沙山月牙泉",
    "description": "沿着沙丘与泉水的交界，想象一段西北旅程。",
    "en": {
      "province": "Gansu",
      "city": "Dunhuang",
      "title": "Crescent Lake & Singing Sand Dunes",
      "description": "Where dunes meet a spring, imagine a journey through China's northwest."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Crescent_Lake_from_the_Singing_Sand_Dunes_(20230918101214).jpg",
    "credit": "N509FZ / Wikimedia Commons；使用 960px 等比缩略图。",
    "license": "CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/"
  },
  {
    "id": "region-northeast",
    "image": imageFor("region-northeast"),
    "region": "东北",
    "province": "黑龙江省",
    "city": "哈尔滨",
    "landmark": "圣索菲亚教堂",
    "title": "圣索菲亚教堂",
    "description": "在砖墙与穹顶的轮廓之间，感受一座城市的不同表情。",
    "en": {
      "province": "Heilongjiang",
      "city": "Harbin",
      "title": "Saint Sophia Cathedral",
      "description": "Between brick walls and the dome, see another face of the city."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Cathedral_of_Holy_Wisdom,_Harbin_5.jpg",
    "credit": "EditQ / Wikimedia Commons",
    "license": "CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/；使用Wikimedia 960px缩略图，未另作编辑"
  },
  {
    "id": "region-southwest",
    "image": imageFor("region-southwest"),
    "region": "西南",
    "province": "重庆市",
    "city": "重庆",
    "landmark": "洪崖洞",
    "title": "洪崖洞",
    "description": "从江畔灯火与山城轮廓，展开一场重庆漫游。",
    "en": {
      "province": "Chongqing",
      "city": "Chongqing",
      "title": "Hongyadong",
      "description": "Riverside lights and a city built on hills: start a Chongqing wander."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Chongqing_Nightscape.jpg",
    "credit": "Jay Huang / Wikimedia Commons；Commons 版本由 Beao 裁去底部 3%；使用 960px 等比缩略图。",
    "license": "CC BY 2.0 — https://creativecommons.org/licenses/by/2.0/"
  },
  {
    "id": "province-fujian",
    "image": imageFor("province-fujian"),
    "region": "华东",
    "province": "福建省",
    "city": "厦门市",
    "landmark": "鼓浪屿",
    "title": "鼓浪屿",
    "description": "从岛屿的屋顶与街巷，开启一段厦门漫游。",
    "en": {
      "province": "Fujian",
      "city": "Xiamen",
      "title": "Gulangyu Island",
      "description": "Begin a Xiamen stroll among the island's rooftops and lanes."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Gulangyu.jpg",
    "credit": "Jakob Montrasio / Wikimedia Commons；使用 960px 等比缩略图。",
    "license": "CC BY 2.0 — https://creativecommons.org/licenses/by/2.0/"
  },
  {
    "id": "province-xizang",
    "image": imageFor("province-xizang"),
    "province": "西藏",
    "city": "拉萨",
    "landmark": "布达拉宫",
    "title": "在拉萨，仰望布达拉宫",
    "description": "沿着拉萨的城市脉络，探索布达拉宫周边的建筑与街巷。",
    "en": {
      "province": "Tibet",
      "city": "Lhasa",
      "title": "Looking up at the Potala Palace in Lhasa",
      "description": "Follow Lhasa's streets and explore the architecture around the Potala Palace."
    },
    "objectPosition": "center 38%",
    "source": "https://commons.wikimedia.org/wiki/File%3APotala.jpg",
    "credit": "Ondřej Žváček (Wikimedia Commons; resized)",
    "license": "CC BY 2.5 — https://creativecommons.org/licenses/by/2.5"
  },
  {
    "id": "province-hainan",
    "image": imageFor("province-hainan"),
    "region": "华南",
    "province": "海南省",
    "city": "三亚市",
    "landmark": "天涯海角",
    "title": "天涯海角",
    "description": "把椰影、沙滩与海风，写进一段三亚旅程。",
    "en": {
      "province": "Hainan",
      "city": "Sanya",
      "title": "Tianya Haijiao",
      "description": "Write palm shadows, sand, and sea breeze into a Sanya trip."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Tianya_Haijiao_-_01.jpg",
    "credit": "Anna Frodesiak / Wikimedia Commons；使用 960px 等比缩略图。",
    "license": "CC0 1.0 — https://creativecommons.org/publicdomain/zero/1.0/"
  },
  {
    "id": "province-shanxi",
    "image": imageFor("province-shanxi"),
    "province": "山西省",
    "city": "大同",
    "landmark": "悬空寺",
    "title": "悬空寺",
    "description": "从崖壁与屋檐的线条里，想象一段不同的远行。",
    "en": {
      "province": "Shanxi",
      "city": "Datong",
      "title": "Hanging Temple",
      "description": "In the lines of cliff and eaves, imagine a different kind of journey."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Hangingtemple20190929.jpg",
    "credit": "Charlie fong / Wikimedia Commons",
    "license": "CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/；Wikimedia 960px缩略图，未另作编辑"
  },
  {
    "id": "province-hongkong",
    "image": imageFor("province-hongkong"),
    "province": "香港",
    "city": "香港",
    "landmark": "维多利亚港",
    "title": "维港入夜，城市灯火亮起",
    "description": "沿着维多利亚港两岸漫步，感受香港的海港与城市天际线。",
    "en": {
      "province": "Hong Kong",
      "city": "Hong Kong",
      "title": "Victoria Harbour lights up at night",
      "description": "Walk both shores of Victoria Harbour and take in Hong Kong's harbour skyline."
    },
    "objectPosition": "center 50%",
    "source": "https://commons.wikimedia.org/wiki/File%3AHong_Kong_Harbour_9.jpg",
    "credit": "Wilfredor (Wikimedia Commons; resized)",
    "license": "CC0 — http://creativecommons.org/publicdomain/zero/1.0/deed.en"
  },
  {
    "id": "province-jilin",
    "image": imageFor("province-jilin"),
    "province": "吉林省",
    "city": "长白山地区",
    "landmark": "长白山天池",
    "title": "长白山天池",
    "description": "在山与水的留白之间，为远行留一点想象。",
    "en": {
      "province": "Jilin",
      "city": "Changbai Mountain",
      "title": "Heaven Lake of Changbai Mountain",
      "description": "Leave a little room for imagination between mountain and water."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Changbaitianchi.jpg",
    "credit": "Qasrawi 2000 / Wikimedia Commons",
    "license": "CC BY-SA 3.0 — https://creativecommons.org/licenses/by-sa/3.0/；原始1024px照片，未编辑"
  },
  {
    "id": "region-south",
    "image": imageFor("region-south"),
    "region": "华南",
    "province": "广东省",
    "city": "广州",
    "landmark": "广州塔",
    "title": "广州塔",
    "description": "跟随夜色里的明亮轮廓，发现城市旅行的另一种节奏。",
    "en": {
      "province": "Guangdong",
      "city": "Guangzhou",
      "title": "Canton Tower",
      "description": "Follow a bright silhouette in the night and find a new rhythm for city travel."
    },
    "source": "https://unsplash.com/photos/the-canton-tower-is-illuminated-with-rainbow-lights-JluPG9ZyCeY",
    "credit": "BIlly Xue / Unsplash",
    "license": "Unsplash License — https://unsplash.com/license；下载为1100px宽JPEG"
  },
  {
    "id": "province-sichuan",
    "image": imageFor("province-sichuan"),
    "region": "西南",
    "province": "四川省",
    "city": "乐山市",
    "landmark": "乐山大佛",
    "title": "乐山大佛",
    "description": "从江畔石壁间的大佛，开启一段乐山文化漫游。",
    "en": {
      "province": "Sichuan",
      "city": "Leshan",
      "title": "Leshan Giant Buddha",
      "description": "Start a cultural trip in Leshan from the Buddha carved into the riverside cliff."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Leshan_Giant_Buddha.jpg",
    "credit": "Bernt Rostad；Rbmk 修改 / Wikimedia Commons；使用 960px 等比缩略图。",
    "license": "CC BY 2.0 — https://creativecommons.org/licenses/by/2.0/"
  },
  {
    "id": "province-jiangsu",
    "image": imageFor("province-jiangsu"),
    "province": "江苏省",
    "city": "苏州",
    "landmark": "拙政园",
    "title": "拙政园",
    "description": "从亭台与水面的倒影里，寻找一段细腻的旅程。",
    "en": {
      "province": "Jiangsu",
      "city": "Suzhou",
      "title": "Humble Administrator's Garden",
      "description": "Find a delicate journey in the reflections of pavilions and ponds."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Humble_Administrator_Garden_48244-Suzhou_(49171762172).jpg",
    "credit": "xiquinhosilva / Wikimedia Commons",
    "license": "CC BY 2.0 — https://creativecommons.org/licenses/by/2.0/；Wikimedia 960px缩略图，未另作编辑"
  },
  {
    "id": "province-ningxia",
    "image": imageFor("province-ningxia"),
    "province": "宁夏",
    "city": "银川",
    "landmark": "西夏王陵",
    "title": "贺兰山下，探寻西夏往事",
    "description": "从西夏王陵出发，把遗址参观与银川城市漫游连在一起。",
    "en": {
      "province": "Ningxia",
      "city": "Yinchuan",
      "title": "Western Xia history beneath the Helan Mountains",
      "description": "Start at the Western Xia Tombs and connect the ruins with a walk through Yinchuan."
    },
    "objectPosition": "center 55%",
    "source": "https://commons.wikimedia.org/wiki/File%3AXi_Xia_Imperial_Tombs_(54154641924).jpg",
    "credit": "xiquinhosilva (Wikimedia Commons; resized)",
    "license": "CC BY 2.0 — https://creativecommons.org/licenses/by/2.0"
  },
  {
    "id": "province-macau",
    "image": imageFor("province-macau"),
    "province": "澳门",
    "city": "澳门",
    "landmark": "大三巴牌坊",
    "title": "从大三巴，走进澳门旧街",
    "description": "从大三巴牌坊延伸到周边街巷，体验澳门的历史城区。",
    "en": {
      "province": "Macau",
      "city": "Macau",
      "title": "From the Ruins of St. Paul's into old Macau",
      "description": "Walk from the Ruins of St. Paul's into the lanes of Macau's historic centre."
    },
    "objectPosition": "center 42%",
    "source": "https://commons.wikimedia.org/wiki/File%3A%E5%A4%A7%E4%B8%89%E5%B7%B4%E7%89%8C%E5%9D%8A.jpg",
    "credit": "GG001213 (Wikimedia Commons; resized)",
    "license": "CC0 — http://creativecommons.org/publicdomain/zero/1.0/deed.en"
  },
  {
    "id": "province-xinjiang",
    "image": imageFor("province-xinjiang"),
    "province": "新疆",
    "city": "阜康",
    "landmark": "天山天池",
    "title": "在天山天池，看山与湖相遇",
    "description": "以天池的湖光山色为线索，规划一段天山北麓的自然之旅。",
    "en": {
      "province": "Xinjiang",
      "city": "Fukang",
      "title": "Where mountains meet the lake at Tianchi",
      "description": "Let Tianchi's lake and peaks guide a nature trip along the northern Tianshan."
    },
    "objectPosition": "center 50%",
    "source": "https://commons.wikimedia.org/wiki/File%3AThe_Heavenly_Lake_%E5%A4%A9%E6%B1%A0_(8064381762).jpg",
    "credit": "Caitriana Nicholson from 北京 ~ Beijing, 中国 ~ China (Wikimedia Commons; resized)",
    "license": "CC BY-SA 2.0 — https://creativecommons.org/licenses/by-sa/2.0"
  },
  {
    "id": "province-zhejiang",
    "image": imageFor("province-zhejiang"),
    "province": "浙江省",
    "city": "杭州",
    "landmark": "西湖",
    "title": "西湖",
    "description": "在湖畔片刻停留，让下一段旅行从容展开。",
    "en": {
      "province": "Zhejiang",
      "city": "Hangzhou",
      "title": "West Lake",
      "description": "Pause by the lake and let your next trip unfold at an easy pace."
    },
    "source": "https://unsplash.com/photos/a-group-of-people-sitting-on-a-bench-next-to-a-body-of-water-WGpESYTfQHE",
    "credit": "xiaoyu xie (@nyenchen) / Unsplash",
    "license": "Unsplash License — https://unsplash.com/license；下载为1100px宽JPEG"
  },
  {
    "id": "province-taiwan",
    "image": imageFor("province-taiwan"),
    "province": "台湾",
    "city": "台北",
    "landmark": "台北101",
    "title": "台北天际线，留给黄昏",
    "description": "以台北101的城市轮廓为起点，探索台北的街区与夜色。",
    "en": {
      "province": "Taiwan",
      "city": "Taipei",
      "title": "Taipei's skyline at dusk",
      "description": "Start from the outline of Taipei 101 and explore the city's neighbourhoods by night."
    },
    "objectPosition": "center 45%",
    "source": "https://commons.wikimedia.org/wiki/File%3ATaipei_101_sunset_skyline_2015.jpg",
    "credit": "中岑 范姜 from Taipei, Taiwan, Republic of China (Wikimedia Commons; resized)",
    "license": "CC BY-SA 2.0 — https://creativecommons.org/licenses/by-sa/2.0"
  },
  {
    "id": "province-hunan",
    "image": imageFor("province-hunan"),
    "region": "华中",
    "province": "湖南省",
    "city": "张家界市",
    "landmark": "张家界武陵源",
    "title": "张家界武陵源",
    "description": "让层叠的石峰与绿意，为下一段山间旅程提供灵感。",
    "en": {
      "province": "Hunan",
      "city": "Zhangjiajie",
      "title": "Wulingyuan, Zhangjiajie",
      "description": "Let layered stone peaks and greenery inspire your next mountain trip."
    },
    "source": "https://commons.wikimedia.org/wiki/File:1_zhangjiajie_huangshizhai_wulingyuan_panorama_2012.jpg",
    "credit": "chensiyuan / Wikimedia Commons；Commons 版本由 Alchemist-hp 去除尘点及降低色差；使用 960px 等比缩略图。",
    "license": "CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/"
  },
  {
    "id": "province-tianjin",
    "image": imageFor("province-tianjin"),
    "province": "天津市",
    "city": "天津",
    "landmark": "天津之眼",
    "title": "天津之眼",
    "description": "沿着城市的曲线，寻找下一段旅程的轻快开场。",
    "en": {
      "province": "Tianjin",
      "city": "Tianjin",
      "title": "Tianjin Eye",
      "description": "Follow the city's curves for a light-hearted start to your next trip."
    },
    "objectPosition": "60% 45%",
    "source": "https://commons.wikimedia.org/wiki/File:Tianjin_Eye_20160514.jpg",
    "credit": "JULIANISME / Wikimedia Commons",
    "license": "CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/；Wikimedia 960px缩略图，未另作编辑"
  },
  {
    "id": "province-yunnan",
    "image": imageFor("province-yunnan"),
    "province": "云南",
    "city": "大理",
    "landmark": "崇圣寺三塔",
    "title": "三塔与苍山，读一页大理",
    "description": "从三塔的古建轮廓出发，串起大理的人文与山间风景。",
    "en": {
      "province": "Yunnan",
      "city": "Dali",
      "title": "Three Pagodas and Cangshan: a page of Dali",
      "description": "From the pagodas' silhouettes, link Dali's culture with its mountain scenery."
    },
    "objectPosition": "center 45%",
    "source": "https://commons.wikimedia.org/wiki/File%3AThree_Pagodas_of_the_Chongsheng_Temple.jpg",
    "credit": "Jackiejackie123123 (Wikimedia Commons; resized)",
    "license": "CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0"
  },
  {
    "id": "province-henan",
    "image": imageFor("province-henan"),
    "region": "华中",
    "province": "河南省",
    "city": "洛阳市",
    "landmark": "龙门石窟",
    "title": "龙门石窟",
    "description": "从河畔石壁上的造像，展开一段洛阳文化之旅。",
    "en": {
      "province": "Henan",
      "city": "Luoyang",
      "title": "Longmen Grottoes",
      "description": "Begin a cultural trip in Luoyang with the carvings on the riverside cliffs."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Grutes_de_longmen.jpg",
    "credit": "Marcdf / Wikimedia Commons；使用 960px 等比缩略图。",
    "license": "Public domain — 作者已将作品发布至公有领域，详见来源页面。"
  },
  {
    "id": "province-neimenggu",
    "image": imageFor("province-neimenggu"),
    "province": "内蒙古自治区",
    "city": "呼伦贝尔",
    "landmark": "呼伦贝尔草原",
    "title": "呼伦贝尔草原",
    "description": "把视线交给辽阔的地平线，让旅行的节奏慢下来。",
    "en": {
      "province": "Inner Mongolia",
      "city": "Hulunbuir",
      "title": "Hulunbuir Grassland",
      "description": "Hand your gaze to the wide horizon and let the journey slow down."
    },
    "objectPosition": "50% 75%",
    "source": "https://commons.wikimedia.org/wiki/File:Hulun_Buir.jpg",
    "credit": "Emmazzye / Wikimedia Commons",
    "license": "CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/；Wikimedia 960px缩略图，未另作编辑"
  },
  {
    "id": "province-guizhou",
    "image": imageFor("province-guizhou"),
    "region": "西南",
    "province": "贵州省",
    "city": "安顺市",
    "landmark": "黄果树瀑布",
    "title": "黄果树瀑布",
    "description": "从倾泻的水流与山林，寻找一段贵州自然之旅。",
    "en": {
      "province": "Guizhou",
      "city": "Anshun",
      "title": "Huangguoshu Waterfall",
      "description": "Find a Guizhou nature trip in rushing water and forested hills."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Huangguoshu_Waterfall_-_Pixabay.jpg",
    "credit": "Robinliu / Pixabay，经 Wikimedia Commons；使用 960px 等比缩略图。",
    "license": "CC0 1.0 — https://creativecommons.org/publicdomain/zero/1.0/"
  },
  {
    "id": "province-shandong",
    "image": imageFor("province-shandong"),
    "region": "华东",
    "province": "山东省",
    "city": "青岛市",
    "landmark": "青岛栈桥",
    "title": "青岛栈桥",
    "description": "沿着海面伸向远处的栈桥，感受青岛的城市轮廓。",
    "en": {
      "province": "Shandong",
      "city": "Qingdao",
      "title": "Zhanqiao Pier",
      "description": "Follow the pier out over the sea and take in Qingdao's outline."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Qingdao_Zhan_Qiao.jpg",
    "credit": "M. Weitzel / Wikimedia Commons；使用 960px 等比缩略图。",
    "license": "CC BY-SA 2.5 — https://creativecommons.org/licenses/by-sa/2.5/"
  },
  {
    "id": "province-qinghai",
    "image": imageFor("province-qinghai"),
    "province": "青海",
    "city": "青海湖周边",
    "landmark": "青海湖",
    "title": "向着青海湖，放慢脚步",
    "description": "沿着青海湖畔的开阔视野，寻找适合停留的高原风景。",
    "en": {
      "province": "Qinghai",
      "city": "Around Qinghai Lake",
      "title": "Slow down by Qinghai Lake",
      "description": "Along the open shores of Qinghai Lake, find plateau views worth stopping for."
    },
    "objectPosition": "center 45%",
    "source": "https://commons.wikimedia.org/wiki/File%3AQinghai_Lake%2C_China_(Unsplash).jpg",
    "credit": "Weichao Deng / juniperphoton (via Unsplash; resized)",
    "license": "CC0 — http://creativecommons.org/publicdomain/zero/1.0/deed.en"
  },
  {
    "id": "province-liaoning",
    "image": imageFor("province-liaoning"),
    "province": "辽宁省",
    "city": "沈阳",
    "landmark": "沈阳故宫",
    "title": "沈阳故宫",
    "description": "循着屋檐的起伏，打开一页城市漫游的想象。",
    "en": {
      "province": "Liaoning",
      "city": "Shenyang",
      "title": "Shenyang Imperial Palace",
      "description": "Follow the rise and fall of the eaves into a city walk."
    },
    "source": "https://commons.wikimedia.org/wiki/File:2014_Manchu_Forbidden_City_Dazheng_Hall_02.jpg",
    "credit": "Gary Todd / Wikimedia Commons",
    "license": "CC0 1.0 — https://creativecommons.org/publicdomain/zero/1.0/；Wikimedia 960px缩略图，未另作编辑"
  },
  {
    "id": "province-jiangxi",
    "image": imageFor("province-jiangxi"),
    "region": "华东",
    "province": "江西省",
    "city": "南昌市",
    "landmark": "滕王阁",
    "title": "滕王阁",
    "description": "循着楼阁的层层飞檐，寻找南昌的人文风景。",
    "en": {
      "province": "Jiangxi",
      "city": "Nanchang",
      "title": "Pavilion of Prince Teng",
      "description": "Trace the pavilion's tiers of eaves to find Nanchang's cultural scenery."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Pavilion_of_Prince_Teng.jpg",
    "credit": "钉钉 / Wikimedia Commons；使用 960px 等比缩略图。",
    "license": "CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/"
  },
  {
    "id": "province-guangxi",
    "image": imageFor("province-guangxi"),
    "region": "华南",
    "province": "广西壮族自治区",
    "city": "桂林市",
    "landmark": "象鼻山",
    "title": "象鼻山",
    "description": "在山与水相接的地方，寻找桂林旅程的起点。",
    "en": {
      "province": "Guangxi",
      "city": "Guilin",
      "title": "Elephant Trunk Hill",
      "description": "Where hill meets river, find the starting point of a Guilin journey."
    },
    "source": "https://commons.wikimedia.org/wiki/File:ElephantTrunkHill.jpg",
    "credit": "Bernt Rostad / Wikimedia Commons；使用 960px 等比缩略图。",
    "license": "CC BY 2.0 — https://creativecommons.org/licenses/by/2.0/"
  },
  {
    "id": "province-anhui",
    "image": imageFor("province-anhui"),
    "province": "安徽省",
    "city": "黄山",
    "landmark": "黄山",
    "title": "黄山",
    "description": "随山峰的轮廓延伸目光，收藏一份新的远行灵感。",
    "en": {
      "province": "Anhui",
      "city": "Huangshan",
      "title": "Mount Huangshan",
      "description": "Let your eyes follow the peaks and keep a new piece of travel inspiration."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Panorama_-_HuangShan.jpg",
    "credit": "Stephane.janel / Wikimedia Commons",
    "license": "CC BY-SA 3.0 — https://creativecommons.org/licenses/by-sa/3.0/；Wikimedia 960px缩略图，未另作编辑"
  },
  {
    "id": "province-hebei",
    "image": imageFor("province-hebei"),
    "province": "河北省",
    "city": "秦皇岛",
    "landmark": "山海关·老龙头",
    "title": "山海关·老龙头",
    "description": "让城墙与海的交汇，成为一段旅行灵感。",
    "en": {
      "province": "Hebei",
      "city": "Qinhuangdao",
      "title": "Shanhai Pass · Old Dragon Head",
      "description": "Let the place where the wall meets the sea inspire a trip."
    },
    "source": "https://commons.wikimedia.org/wiki/File:ShanhaiguanGreatWall-end.jpg",
    "credit": "fuzheado / Wikimedia Commons",
    "license": "CC BY 2.0 — https://creativecommons.org/licenses/by/2.0/；Wikimedia 960px缩略图，未另作编辑"
  },
  {
    "id": "region-central",
    "image": imageFor("region-central"),
    "region": "华中",
    "province": "湖北省",
    "city": "武汉",
    "landmark": "黄鹤楼",
    "title": "黄鹤楼",
    "description": "在飞檐与蓝天下，寻找一段武汉城市漫游的灵感。",
    "en": {
      "province": "Hubei",
      "city": "Wuhan",
      "title": "Yellow Crane Tower",
      "description": "Under flying eaves and blue sky, find inspiration for a Wuhan city walk."
    },
    "source": "https://commons.wikimedia.org/wiki/File:Yellow_Crane_Tower,_2013_photo.jpg",
    "credit": "Meraj Chhaya / Wikimedia Commons；使用 960px 等比缩略图。",
    "license": "CC BY 2.0 — https://creativecommons.org/licenses/by/2.0/"
  },
  {
    "id": "province-shaanxi",
    "image": imageFor("province-shaanxi"),
    "province": "陕西",
    "city": "西安",
    "landmark": "秦始皇兵马俑",
    "title": "走近西安，遇见千年秦俑",
    "description": "以兵马俑为起点，安排一段认识西安历史的文化行程。",
    "en": {
      "province": "Shaanxi",
      "city": "Xi'an",
      "title": "Meet the Terracotta Army in Xi'an",
      "description": "Start with the Terracotta Army and plan a cultural trip through Xi'an's history."
    },
    "objectPosition": "center 50%",
    "source": "https://commons.wikimedia.org/wiki/File%3A51714-Terracota-Army.jpg",
    "credit": "xiquinhosilva (Wikimedia Commons; resized)",
    "license": "CC BY 2.0 — https://creativecommons.org/licenses/by/2.0"
  }
]

const LICENSE_URL = /https?:\/\/[^\s；]+/

/** Short license label, e.g. "CC BY-SA 4.0" or "Unsplash License". */
export const licenseLabel = (d: Destination): string => d.license.split(' — ')[0].split('；')[0].trim()

/** License URL embedded in the license string, if any. */
export const licenseUrl = (d: Destination): string | undefined => d.license.match(LICENSE_URL)?.[0]

/** Author part of the credit, without the resize note. */
export const creditLabel = (d: Destination): string => d.credit.split('；')[0].trim()

/** Strip administrative suffixes so 上海市 and 上海 compare equal. */
export const shortRegionName = (value: string): string =>
  value.replace(/特别行政区|维吾尔自治区|壮族自治区|回族自治区|自治区|省|市/g, '')
