const configuredApiBase = import.meta.env.VITE_API_BASE_URL?.trim()
const devDefaultApiBase = window.location.port === '5173' ? 'http://127.0.0.1:8000' : ''

export const API_BASE_URL = (configuredApiBase || devDefaultApiBase).replace(/\/+$/, '')
