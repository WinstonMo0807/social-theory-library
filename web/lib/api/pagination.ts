export type Paginated<T> = {
  count: number;
  results: T[];
  next?: string | null;
  previous?: string | null;
};

export type DirectoryPage<T> = {
  count: number;
  results: T[];
  page: number;
  pageSize: number;
  totalPages: number;
};

export function directoryPage<T>(payload: Paginated<T>, page: number, pageSize = 24): DirectoryPage<T> {
  return {
    count: payload.count,
    results: payload.results,
    page,
    pageSize,
    totalPages: payload.count ? Math.ceil(payload.count / pageSize) : 0,
  };
}
