import Link from "next/link";

export default function LandingPage() {
  return (
    <>
      <div className="card">
        <h2>終了直前の自動入札で、競り上げずに落札する</h2>
        <p>
          商品URLと上限金額を登録するだけで、オークション終了の直前(5〜300秒前で設定可)に
          自動で入札します。終了時刻に張り付く必要はありません。電源OFFでもサーバー側で実行されます。
        </p>
        <ul>
          <li>自動延長ありの商品は、延長を検知して上限額の範囲内で再入札</li>
          <li>落札・敗北・失敗はすべてメールで通知</li>
          <li>Yahoo! JAPAN のパスワードはお預かりしません(ログインセッションのみを暗号化保管)</li>
        </ul>
        <Link href="/register">
          <button>無料で始める</button>
        </Link>
      </div>
      <div className="card">
        <h2>ご利用上の注意</h2>
        <p className="muted">
          本サービスは入札操作の予約代行ツールです。外部ツールによる自動入札はヤフオクの
          運営方針によりアカウント利用が制限されるリスクがあります。回線・仕様変更等により
          入札が実行できない場合があり、落札機会の損失は補償されません。
          初回登録時にこれらへの同意をお願いしています。
        </p>
      </div>
    </>
  );
}
