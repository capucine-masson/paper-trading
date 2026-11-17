const BASE = import.meta.env.BASE_URL;

export function Cat() {
  return (
    <picture className="cat" aria-hidden="true">
      <source media="(prefers-reduced-motion: reduce)" srcSet={`${BASE}cat-idle-still.png`} />
      <img src={`${BASE}cat-idle.gif`} alt="" />
    </picture>
  );
}
