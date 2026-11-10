import { useCallback, useEffect, useState } from 'react'

// Load data when inputs change. Ignores responses that arrive after the inputs changed again,
// so a slow request for Monday can't overwrite the slots for Tuesday.
export default function useLoad(loader, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [version, setVersion] = useState(0)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(loader, deps)

  useEffect(() => {
    let current = true
    setState((s) => ({ ...s, loading: true, error: null }))
    load()
      .then((data) => current && setState({ data, error: null, loading: false }))
      .catch((error) => current && setState({ data: null, error, loading: false }))
    return () => {
      current = false
    }
  }, [load, version])

  const reload = useCallback(() => setVersion((v) => v + 1), [])
  return { ...state, reload }
}
