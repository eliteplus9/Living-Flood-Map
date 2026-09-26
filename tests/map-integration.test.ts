import { expect, it } from "vitest";
import { rowsToTweets } from "../frontend/src/csv";
import { groupPlaces } from "../frontend/src/mapData";

it("groups valid shared coordinates without duplicating a tweet or plotting unresolved points", () => {
  const source = rowsToTweets([{ tweet: "Flood in Calgary" }], "tweet")[0];
  const place = { tweet_id: source.tweet_id, mention: "Calgary", canonical_name: "Calgary", latitude: 51, longitude: -114, location_score: .8, status: "resolved" as const };
  const grouped = groupPlaces([{ ...source, locations: [place, place, { ...place, status: "ambiguous" }] }]);
  expect(grouped).toHaveLength(1);
  expect(grouped[0].reports).toHaveLength(1);
  expect(groupPlaces([{ ...source, locations: [{ ...place, latitude: Number.NaN }] }])).toHaveLength(0);
});
