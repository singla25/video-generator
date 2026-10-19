/** Route placeholder until the real screen lands in a later task. */
export function PlaceholderPage({ name }: { name: string }) {
  return <p className="text-muted">{name} is coming soon.</p>;
}
