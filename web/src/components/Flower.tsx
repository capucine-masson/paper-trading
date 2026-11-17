const BASE = import.meta.env.BASE_URL;

export function Flower() {
  return (
    <span className="flower" aria-hidden="true">
      <img src={`${BASE}Icon-Model-Small-stem.png`} alt="" />
      <img className="flower-head" src={`${BASE}Icon-Model-Small-head.png`} alt="" />
    </span>
  );
}
