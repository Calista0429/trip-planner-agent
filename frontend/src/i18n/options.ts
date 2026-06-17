import { computed, type ComputedRef } from 'vue'
import { locale } from './index'

// Each option keeps a stable `value` (sent to the backend — Chinese strings for
// transportation/accommodation/preferences must NOT change) and per-locale
// display labels. Only the label switches with the language toggle.
interface RawOption {
  value: string
  zh: string
  en: string
  icon?: string
}

export interface LocalizedOption {
  value: string
  label: string
  icon?: string
}

function localize(list: RawOption[]): ComputedRef<LocalizedOption[]> {
  return computed(() =>
    list.map((o) => ({
      value: o.value,
      label: locale.value === 'en' ? o.en : o.zh,
      icon: o.icon
    }))
  )
}

const companionType: RawOption[] = [
  { value: 'solo', zh: '独行', en: 'Solo' },
  { value: 'couple', zh: '情侣', en: 'Couple' },
  { value: 'friends', zh: '朋友', en: 'Friends' },
  { value: 'family_with_children', zh: '亲子', en: 'Family with kids' },
  { value: 'family_with_elders', zh: '带长辈', en: 'With elders' },
  { value: 'business', zh: '商务', en: 'Business' },
  { value: 'other', zh: '其他', en: 'Other' }
]

const budgetLevel: RawOption[] = [
  { value: 'limited', zh: '节省', en: 'Budget' },
  { value: 'standard', zh: '标准', en: 'Standard' },
  { value: 'comfortable', zh: '舒适', en: 'Comfortable' },
  { value: 'premium', zh: '高端', en: 'Premium' },
  { value: 'luxury', zh: '奢华', en: 'Luxury' }
]

const transportation: RawOption[] = [
  { value: '公共交通', zh: '公共交通', en: 'Public transit' },
  { value: '地铁公交', zh: '地铁公交', en: 'Metro & bus' },
  { value: '打车/网约车', zh: '打车/网约车', en: 'Taxi / ride-hailing' },
  { value: '自驾', zh: '自驾', en: 'Self-drive' },
  { value: '租车自驾', zh: '租车自驾', en: 'Rental car' },
  { value: '包车/私人司机', zh: '包车/私人司机', en: 'Chartered car / driver' },
  { value: '高铁+市内交通', zh: '高铁+市内交通', en: 'High-speed rail + local' },
  { value: '飞机+市内交通', zh: '飞机+市内交通', en: 'Flight + local' },
  { value: '骑行/步行', zh: '骑行/步行', en: 'Cycling / walking' },
  { value: '混合交通', zh: '混合交通', en: 'Mixed transport' },
  { value: '无障碍交通优先', zh: '无障碍交通优先', en: 'Accessibility-first' }
]

const accommodation: RawOption[] = [
  { value: '经济型酒店', zh: '经济型酒店', en: 'Budget hotel' },
  { value: '舒适型酒店', zh: '舒适型酒店', en: 'Comfort hotel' },
  { value: '高端酒店', zh: '高端酒店', en: 'Upscale hotel' },
  { value: '豪华酒店', zh: '豪华酒店', en: 'Luxury hotel' },
  { value: '亲子酒店', zh: '亲子酒店', en: 'Family hotel' },
  { value: '民宿', zh: '民宿', en: 'B&B / homestay' }
]

const preference: RawOption[] = [
  { value: '历史文化', zh: '历史文化', en: 'History & culture', icon: '🏛️' },
  { value: '自然风光', zh: '自然风光', en: 'Nature & scenery', icon: '🏞️' },
  { value: '美食', zh: '美食探店', en: 'Food & dining', icon: '🍜' },
  { value: '购物', zh: '购物商圈', en: 'Shopping', icon: '🛍️' },
  { value: '艺术', zh: '艺术展览', en: 'Art & exhibitions', icon: '🎨' },
  { value: '休闲', zh: '休闲放松', en: 'Leisure & relaxation', icon: '☕' },
  { value: '亲子友好', zh: '亲子友好', en: 'Family-friendly', icon: '🧸' },
  { value: '老人友好', zh: '老人友好', en: 'Elder-friendly', icon: '🧓' },
  { value: '小众路线', zh: '小众路线', en: 'Off the beaten path', icon: '🧭' },
  { value: '夜游', zh: '夜游体验', en: 'Nightlife', icon: '🌃' },
  { value: '摄影打卡', zh: '摄影打卡', en: 'Photography spots', icon: '📷' },
  { value: '博物馆', zh: '博物馆', en: 'Museums', icon: '🏺' },
  { value: '城市漫步', zh: '城市漫步', en: 'City walks', icon: '🚶' },
  { value: '户外徒步', zh: '户外徒步', en: 'Hiking', icon: '🥾' },
  { value: '主题乐园', zh: '主题乐园', en: 'Theme parks', icon: '🎢' },
  { value: '避开人群', zh: '避开人群', en: 'Avoid crowds', icon: '🌿' }
]

export const companionTypeOptions = localize(companionType)
export const budgetLevelOptions = localize(budgetLevel)
export const transportationOptions = localize(transportation)
export const accommodationOptions = localize(accommodation)
export const preferenceOptions = localize(preference)
