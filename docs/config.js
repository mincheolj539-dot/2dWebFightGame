// 대전 서버 주소 설정.
//
// 로컬(localhost/127.0.0.1)에서 열면 자동으로 로컬 대전 서버(ws://localhost:8765)를 쓰고,
// 배포된 사이트에서 열면 아래 PROD 주소를 쓴다.
// URL 에 ?server=... 를 붙이면 무엇이든 덮어쓸 수 있다.
(function () {
  // 배포 서버 = NAS(Docker) + DSM 역방향 프록시. 인증서가 붙은 443 을 통해 wss 로 접속.
  var PROD = "wss://minicheolgwon.p-e.kr";
  var LOCAL = "ws://localhost:8765";               // 로컬 서버 (python server/server.py)
  var host = location.hostname;
  var isLocal = (host === "localhost" || host === "127.0.0.1" || host === "");
  window.GAME_SERVER = isLocal ? LOCAL : PROD;
})();
