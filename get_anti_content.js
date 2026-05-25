// 生成拼多多 anti_content token
// 用法: node get_anti_content.js
window = global;
require('./anti_content.js');

var anti_contnt = xjb(5);
result = new anti_contnt({serverTime: new Date().getTime()});
console.log(result.messagePack());
