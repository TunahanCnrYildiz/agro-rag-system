import { useEffect, useState } from "react";
import {
  Article,
  CatalogProduct,
  fetchArticles,
  fetchProducts,
} from "./api";

// Simple module-level cache so the list screen and detail screen share the
// same fetched data for the app session, without a full state-management
// library or refetching per navigation.
let productsCache: CatalogProduct[] | null = null;
let articlesCache: Article[] | null = null;

interface FetchState<T> {
  data: T[];
  loading: boolean;
  error: string | null;
}

export function useProducts(): FetchState<CatalogProduct> {
  const [state, setState] = useState<FetchState<CatalogProduct>>({
    data: productsCache ?? [],
    loading: productsCache === null,
    error: null,
  });

  useEffect(() => {
    if (productsCache !== null) return;
    fetchProducts()
      .then((data) => {
        productsCache = data;
        setState({ data, loading: false, error: null });
      })
      .catch((e) =>
        setState({ data: [], loading: false, error: String(e) })
      );
  }, []);

  return state;
}

export function useArticles(): FetchState<Article> {
  const [state, setState] = useState<FetchState<Article>>({
    data: articlesCache ?? [],
    loading: articlesCache === null,
    error: null,
  });

  useEffect(() => {
    if (articlesCache !== null) return;
    fetchArticles()
      .then((data) => {
        articlesCache = data;
        setState({ data, loading: false, error: null });
      })
      .catch((e) =>
        setState({ data: [], loading: false, error: String(e) })
      );
  }, []);

  return state;
}

export function findProductByUrl(url: string): CatalogProduct | undefined {
  return productsCache?.find((p) => p.source_url === url);
}

export function findArticleByUrl(url: string): Article | undefined {
  return articlesCache?.find((a) => a.source_url === url);
}
