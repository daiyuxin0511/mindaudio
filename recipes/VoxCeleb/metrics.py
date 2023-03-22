def compute_fa_miss(scores, labels, pos_label=1, return_thresholds=True):
    """Returns P_fa, P_miss, [thresholds]
    """
    from sklearn.metrics import roc_curve
    fpr, tpr, thresholds = roc_curve(labels, scores, pos_label=pos_label)
    P_fa = fpr[::-1]
    P_miss = 1. - tpr[::-1]
    thresholds = thresholds[::-1]
    if return_thresholds:
        return P_fa, P_miss, thresholds
    return P_fa, P_miss


def get_EER(P_fa, P_miss, thresholds=None):
    """Compute EER given false alarm and miss probabilities
    """
    from scipy.optimize import brentq
    from scipy.interpolate import interp1d
    eer = brentq(lambda x: x - interp1d(P_fa, P_miss)(x), 0., 1.)
    eer = float(eer)
    if thresholds is None:
        return eer
    thresh_eer = interp1d(P_fa, thresholds)(eer)
    thresh_eer = float(thresh_eer)
    return eer, thresh_eer


def get_EER_from_scores(scores, labels, pos_label=1):
    """Compute EER given scores and labels
    """
    P_fa, P_miss, thresholds = compute_fa_miss(scores, labels, pos_label,
                                               return_thresholds=True)
    eer, thresh_eer = get_EER(P_fa, P_miss, thresholds)
    return eer, thresh_eer
