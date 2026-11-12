import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listReviews } from '../api'
import NewReviewModal from '../components/NewReviewModal'

export default function HomePage() {
  const [reviews, setReviews] = useState([])
  const [error, setError] = useState(null)
  const [showModal, setShowModal] = useState(false)

  useEffect(() => {
    listReviews().then(setReviews).catch((e) => setError(e.message))
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">CV Reviews</h1>
        <button
          onClick={() => setShowModal(true)}
          className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700"
        >
          New Review
        </button>
      </div>
      {error && <p className="text-red-600">{error}</p>}
      {reviews.length === 0 && !error && (
        <p className="text-gray-500">No reviews yet. Upload a CV and paste a job description to get started.</p>
      )}
      <ul className="space-y-3">
        {reviews.map((r) => (
          <li key={r.id}>
            <Link to={`/reviews/${r.id}`} className="block bg-white border rounded-lg p-4 hover:border-indigo-300 dark:bg-gray-800 dark:border-gray-700 dark:hover:border-indigo-500">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">Review #{r.id}</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-1 max-w-xl">{r.jd_text}</p>
                </div>
                <div className="text-right">
                  <p className={`text-xl font-bold ${r.current_score >= 70 ? 'text-green-600' : r.current_score >= 40 ? 'text-yellow-600' : 'text-red-600'}`}>
                    {r.current_score}%
                  </p>
                  <p className="text-xs text-gray-400">{r.status}</p>
                </div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {showModal && <NewReviewModal onClose={() => setShowModal(false)} />}
    </div>
  )
}
