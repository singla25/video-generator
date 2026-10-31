interface Props {
  page: number;
  pages: number;
  onPage: (page: number) => void;
}

/** Previous and next buttons with "Page X of Y"; the buttons stop at the first and last page. */
export function Pager({ page, pages, onPage }: Props) {
  return (
    <div className="mt-4 flex items-center justify-end gap-3 text-sm">
      <button
        type="button"
        className="rounded-full border px-3 py-1 disabled:opacity-50"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        Previous page
      </button>
      <span>{`Page ${page} of ${pages}`}</span>
      <button
        type="button"
        className="rounded-full border px-3 py-1 disabled:opacity-50"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Next page
      </button>
    </div>
  );
}
