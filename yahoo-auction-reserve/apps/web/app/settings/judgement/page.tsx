import Link from "next/link";
import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import JudgementForm from "./JudgementForm";

export const dynamic = "force-dynamic";

export default async function JudgementSettingsPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  return (
    <>
      <div className="page-head">
        <h1>判断材料</h1>
        <Link href="/settings">設定に戻る</Link>
      </div>
      <div className="card">
        <JudgementForm
          initial={{
            sellerRatingFloor:
              user.sellerRatingFloor === null ? "" : String(user.sellerRatingFloor),
            sellerRatingMinCount:
              user.sellerRatingMinCount === null ? "" : String(user.sellerRatingMinCount),
            blockLowRatedSeller: user.blockLowRatedSeller,
          }}
        />
      </div>
    </>
  );
}
