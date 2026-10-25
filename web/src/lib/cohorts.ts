import type { IndexExport } from "../types/contracts";
import type { Point } from "./headline";
export function cohortIndex(
  cohorts: NonNullable<IndexExport["data"]["cohorts"]>,
  selection: string,
): Point[] {
  const rows = cohorts.filter(
    (row) => `${row.make} / ${row.model}` === selection,
  );
  const weeks = [...new Set(rows.map((row) => row.week))].sort();
  if (weeks.length < 2) return [];
  const points: Point[] = [{ week: weeks[0], value: 100 }];
  for (let index = 1; index < weeks.length; index++) {
    if (
      Date.parse(weeks[index]) - Date.parse(weeks[index - 1]) !==
      7 * 86400000
    )
      return [];
    const previous = rows.filter((row) => row.week === weeks[index - 1]);
    const current = rows.filter((row) => row.week === weeks[index]);
    let weight = 0,
      total = 0;
    for (const row of previous) {
      const match = current.find(
        (candidate) => candidate.model_year === row.model_year,
      );
      if (match && row.median_price_pkr > 0) {
        weight += row.listings;
        total += (row.listings * match.median_price_pkr) / row.median_price_pkr;
      }
    }
    if (!weight) return [];
    points.push({
      week: weeks[index],
      value: (points[index - 1].value * total) / weight,
    });
  }
  return points;
}
