export const ma144ExitStrategyOptions = [
    { value: 'MA20MA144CrossExitLongShortStrategy', label: '20/144多空入场·20/144交叉离场（反手）', reverses: true },
    { value: 'MA20MA144CrossExitLongOnlyStrategy', label: '20/144金叉做多·20/144死叉离场（只做多）' },
    { value: 'MA20MA144CrossExitShortOnlyStrategy', label: '20/144死叉做空·20/144金叉离场（只做空）' },
].map(option => ({ ...option, defaults: { fast_period: 20, slow_period: 144, exit_period: 144 } }));

export const getMA144ExitStrategy = name => ma144ExitStrategyOptions.find(option => option.value === name);
