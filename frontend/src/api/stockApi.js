import axios from "axios";

const BASE_URL = "http://localhost:8000";

async function get(path, params) {
  const response = await axios.get(`${BASE_URL}${path}`, { params });
  return response.data;
}

// Overview needs market cap/PE/EPS/beta, which only this endpoint returns.
export const fetchFundamentals = (ticker) => get(`/stock/${ticker}/fundamentals`);

export const fetchPrice = (ticker, period = "1y") => get(`/stock/${ticker}/price`, { period });
export const fetchFundamental = (ticker) => get(`/stock/${ticker}/fundamental`);
export const fetchValuation = (ticker) => get(`/stock/${ticker}/valuation`);
export const fetchTechnical = (ticker, period = "1y") => get(`/stock/${ticker}/technical`, { period });
export const fetchVolume = (ticker, period = "1y") => get(`/stock/${ticker}/volume`, { period });
export const fetchRisk = (ticker, period = "2y") => get(`/stock/${ticker}/risk`, { period });
export const fetchInstitutional = (ticker) => get(`/stock/${ticker}/institutional`);
export const fetchSentiment = (ticker) => get(`/stock/${ticker}/sentiment`);
export const fetchEarnings = (ticker) => get(`/stock/${ticker}/earnings`);
export const fetchQuantitative = (ticker, period = "3y") => get(`/stock/${ticker}/quantitative`, { period });
export const fetchSocial = (ticker) => get(`/stock/${ticker}/social`);
export const fetchGeopolitical = (ticker) => get(`/stock/${ticker}/geopolitical`);
export const fetchPolitical = (ticker) => get(`/stock/${ticker}/political`);
export const fetchMacro = (ticker) => get(`/stock/${ticker}/macro`);
export const fetchCalendar = (ticker) => (ticker ? get(`/stock/${ticker}/calendar`) : get(`/calendar`));
export const fetchSummary = (ticker) => get(`/stock/${ticker}/summary`);
