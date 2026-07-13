import axios from "axios";

// With the Vite proxy, /api/* and /auth/* are forwarded to the FastAPI backend.
// withCredentials ensures the httpOnly cookie is sent on every request.
const api = axios.create({
  withCredentials: true,
});

// Redirect to landing page on 401 (session expired or not logged in)
api.interceptors.response.use(
  r => r,
  err => {
    if (
      err.response?.status === 401 &&
      !window.location.pathname.startsWith("/")
    ) {
      window.location.href = "/";
    }
    return Promise.reject(err);
  }
);

export default api;
