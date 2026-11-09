import axios from 'axios';

// Same-origin /api is proxied by Vite; deployments may set an API origin.
const api = axios.create({ baseURL: import.meta.env?.VITE_API_BASE_URL || '' });
api.isCancel = axios.isCancel;
export default api;
