const BASE = import.meta.env.BASE_URL;

export function Signpost() {
  return (
    <span className="signpost" aria-hidden="true">
      <img className="signpost-base" src={`${BASE}Icon-Model-Classifier-base.png`} alt="" />
      <img className="signpost-board" src={`${BASE}Icon-Model-Classifier-board.png`} alt="" />
    </span>
  );
}
