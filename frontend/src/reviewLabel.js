export function reviewLabel(review) {
  if (!review?.jd_title) return `Review #${review.id}`
  const company = review.jd_company ? ` at ${review.jd_company}` : ''
  return `Review for ${review.jd_title}${company}`
}
