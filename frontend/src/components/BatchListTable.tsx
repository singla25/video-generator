import { Link } from 'react-router-dom';

import type { Batch } from '../api/types';
import { formatDate, formatNumber, formatProgress } from '../format';

const HEADERS = ['Batch', 'Template', 'Progress', 'Rows', 'Created'];

/** "100 rows", plus " · 10 failed" when some rows failed. */
function rowsLabel(batch: Batch): string {
  const { total, failed } = batch.counts;
  const rows = `${formatNumber(total)} rows`;
  return failed > 0 ? `${rows} · ${formatNumber(failed)} failed` : rows;
}

interface Props {
  batches: Batch[];
  templateNames: Map<string, string>;
}

/** Batches of one dashboard list: name link, template, progress, row counts and creation date. */
export function BatchListTable({ batches, templateNames }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-muted">
          <tr>
            {HEADERS.map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {batches.map((b) => (
            <tr key={b.id} className="border-t">
              <td className="px-3 py-2">
                <Link to={`/batches/${b.id}`} className="font-semibold text-emerald underline">
                  {b.sheet_name || b.folder_name || 'Batch'}
                </Link>
              </td>
              <td className="px-3 py-2">{templateNames.get(b.template_id) ?? '-'}</td>
              <td className="px-3 py-2">{formatProgress(b.counts)}</td>
              <td className="px-3 py-2">{rowsLabel(b)}</td>
              <td className="px-3 py-2">{formatDate(b.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
