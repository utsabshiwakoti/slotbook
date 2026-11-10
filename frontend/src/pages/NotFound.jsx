import { Link } from 'react-router'

export default function NotFound({ message = "We couldn't find that page." }) {
  return (
    <div className="centered">
      <div className="card narrow">
        <h1>Not found</h1>
        <p>{message}</p>
        <Link to="/" className="button">Go home</Link>
      </div>
    </div>
  )
}
