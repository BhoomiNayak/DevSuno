// Example B: the off-by-one loop.
//
// Bug: the loop condition is `i <= arr.length`, so on the last iteration
// it reads arr[arr.length], which does not exist (undefined). The fix is
// a strict bound: `i < arr.length`.
//
// Demo question to speak (Hinglish): "ye loop last element pe kyun
// undefined de raha hai"

function sumAll(arr) {
  let total = 0;
  for (let i = 0; i <= arr.length; i++) {
    total += arr[i];
  }
  return total;
}

module.exports = { sumAll };
