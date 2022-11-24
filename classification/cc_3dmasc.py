# coding: utf-8
# Paul Leroy
# Baptiste Feldmann

import os

import numpy as np
import sklearn.metrics as metrics
from sklearn.preprocessing import MinMaxScaler

from ..tools import cloudcompare, las, misc, PySBF
from ..config.config import EXPORT_FMT, QUERY_0, SHIFT


convention: dict[str, str] = {"gpstime": "gps_time",
                              "numberofreturns": "number_of_returns",
                              "returnnumber": "return_number",
                              "scananglerank": "scan_angle_rank",
                              "pointsourceid": "point_source_id"}


def compute_features_work(query0_params, workspace, params, training_file):
    """
    Call 3DMASC plugin (from CloudCompare) to compute geometric features
    
    Parameters
    ----------
    query0_params : list of string parameters [QUERY_0,EXPORT_FMT,shiftname]
    workspace : str, absolutepath to directory
    params : dict of files to use 3DMASC, [pcx,pc1,PC2,CTX]
    training_file : str, parameters file for 3DMASC
    """
    for i in params.keys():
        if not os.path.exists(workspace + params[i]):
            raise OSError("File " + params[i] + " not found !")

    query = QUERY_0[query0_params[0]] + EXPORT_FMT[query0_params[1]]
    for i in params.keys():
        query += " -o -global_shift " + SHIFT[query0_params[2]] + " " + workspace + params[i]

    query += " -3dmasc_classify -only_features " + training_file + ' "'
    compt = 1
    for i in params.keys():
        query += i + '=' + str(compt) + ' '
        compt += 1

    query = query[0:-1] + '" -save_clouds'
    misc.run(query)
    
    today = misc.DATE()
    if query0_params[1] == "SBF":
        cloudcompare.last_file(workspace + "_".join([params["pcx"][0:-4], "WITH_FEATURES", today.date, "*.sbf"]),
                               params["pcx"][0:-4] + "_features.sbf")
        cloudcompare.last_file(workspace + "_".join([params["pcx"][0:-4], "WITH_FEATURES", today.date, "*.sbf.data"]),
                               params["pcx"][0:-4] + "_features.sbf.data")
        for i in params.keys():
            temp_file = cloudcompare.last_file(workspace + "_".join([params[i][0:-4], today.date, "*.sbf"]))
            os.remove(temp_file)
            temp_file = cloudcompare.last_file(workspace + "_".join([params[i][0:-4], today.date, "*.sbf.data"]))
            os.remove(temp_file)
    
    elif query0_params[1] == "LAS":
        cloudcompare.last_file(workspace + "_".join([params[i][0:-4], "WITH_FEATURES", today.date, "*.laz"]),
                               params["pcx"][0:-4] +"_features.laz")
        for i in params.keys():                
            temp_file = cloudcompare.last_file(workspace + "_".join([params[i][0:-4], today.date, "*.laz"]))
            os.remove(temp_file)

    else:
        raise NotImplementedError("Features can only be exported in SBF or LAS format for now")


def compute_features(workspace, pcx, params_cc, params_features):
    params_training = {"pc1": "_".join(["pc1"] + pcx.split("_")[1::]),
                       "pcx": pcx,
                       "CTX": "_".join(["CTX"] + pcx.split("_")[1::])}

    compute_features_work(params_cc, workspace, params_training, params_features)

    os.rename(workspace + pcx[0:-4] + "_features.sbf",
              workspace + "features/" + pcx[0:-4] + "_features.sbf")
    os.rename(workspace + pcx[0:-4] + "_features.sbf.data",
              workspace + "features/" + pcx[0:-4] + "_features.sbf.data")


def load_features(pcx_filepath, training_filepath, labels=False):
    """
    Loading computed features after using 3DMASC plugin

    Parameters
    ---------
    pcx_filepath : str, absolute path to core-points file
    training_filepath : str, parameters file for 3DMASC
    labels : bool (default=False), in case of training model you need the labels

    Returns
    --------
    data : dict,
         'features' : numpy.array of computed features
         'names' : list of str, name of each column feature
         'labels' : list of int, class labels
    """
    f = PySBF.File(pcx_filepath)
    points = f.points
    names = f.scalarNames
    del f

    tab = np.loadtxt(training_filepath[0:-4]+"_feature_sources.txt",str)
    list_sf = []
    for i in tab:
        name = i.split(sep=':')[1].lower()
        if name in convention.keys():
            list_sf += [convention[name]]
        else:
            list_sf += [name]
    idx_select = list(np.sort([names.index(i) for i in list_sf]))

    data = {"features": points[:, idx_select], "names": list(np.array(names)[idx_select])}
    if labels:
        data["labels"] = points[:, names.index('classification')]
    return data


def accuracy_score(labels_true, labels_pred):
    labels = np.unique(labels_true)
    tab = metrics.confusion_matrix(labels_true, labels_pred, labels)
    list_accuracy = []
    for i in range(0, len(labels)):
        list_accuracy += [tab[i, i] / np.sum(tab[:, i])]
    return list_accuracy, labels


def confidence_score(labels_pred,ind_confid):
    labels = np.unique(labels_pred)
    ind_list = []
    for i in labels:
        temp = labels_pred == i
        ind_list += [np.percentile(ind_confid[temp], 25)]
    return ind_list,labels


def classification_report(labels_true, labels_pred, ind_confid=None, save=False):
    labels = np.unique(labels_true)
    tab = metrics.confusion_matrix(labels_true, labels_pred, labels)
    display = "Confusion matrix :\n\t"
    for i in labels:
        display += str(i) + "\t"
    display += "\n"
    for i in range(0, len(labels)):
        display += str(labels[i]) + "\t"
        for c in range(0, len(labels)):
            display += str(tab[i, c]) + "\t"
        display += "\n"

    result_accuracy = accuracy_score(labels_true, labels_pred)
    if len(ind_confid) > 0:
        result_confid = confidence_score(labels_pred, ind_confid)
    else:
        result_confid = np.array([0] * len(np.unique(labels_pred)))
    
    display2 = "Classes     \t"
    for i in result_accuracy[1]:
        display2 += str(i) + "\t"
    display2 += "\nPrecision  \t"
    for i in result_accuracy[0]:
        display2 += str(np.round_(i * 100, 1)) + "\t"
    display2 += "\nInd_conf 25%\t"
    for i in result_confid[0]:
        display2 += str(np.round_(i * 100, 1)) + "\t"
    display2 += "\n"
    
    test = (labels_true == labels_pred)
    val_true = len([i for i, X in enumerate(test) if X])
    print(display)
    print(display2)
    print("Pourcentage valeur Vrai : %.1f%%" % (val_true / len(test) * 100))
    print("Kappa coefficient: " + str(metrics.cohen_kappa_score(labels_true, labels_pred)))
    print(metrics.classification_report(labels_true, labels_pred, labels))
    
    if save:
        f = open(save, "w")
        print(display + "\n", file=f)
        print(display2, file=f)
        print("Percents of true value: %.1f%%" %(val_true / len(test) * 100), file=f)
        print("Kappa coefficient: " + str(metrics.cohen_kappa_score(labels_true, labels_pred)), file=f)
        print(metrics.classification_report(labels_true, labels_pred, labels), file=f)
        f.close()

        
def feature_importance_analysis(tab, nb_scales):
    """
    Feature Importance Analysis
    (by features and by scales)
    """
    if len(tab) % nb_scales == 0:
        nb_feat = int(len(tab) / nb_scales)
    else:
        raise ValueError("Length of your array doesn't match exactly number of scales")

    by_feat = []
    for i in range(0, nb_feat):
        p = np.arange(0, nb_scales) + (i * nb_scales)
        by_feat += [np.sum(tab[p])]

    by_scales = []
    for i in range(0, nb_scales):
        p = [nb_scales * m + i for m in range(0, nb_feat)]
        by_scales += [np.sum(tab[p])]
        
    print("Feature Importances Analysis :\n\t-By features :")
    print(by_feat)
    print("\t-By scales :")
    print(by_scales)


def correlation(data, names, save=""):
    func = getattr(getattr(__import__("scipy"), "stats"), "pearsonr")
    list_ = []
    for i in range(0, len(data[0, :])):
        temp = []
        for c in range(0, len(data[0, :])):
            if c < i + 1:
                temp += [-2]
            else:
                result = func(data[:, i], data[:, c])[0]
                temp += [round(result, 4)]
                if result > 0.75:
                    print("Correlation between : %s and %s (%.4f)" % (names[i], names[c], result))
        list_ += [temp]
    if len(save) > 0:
        np.savetxt(save, list_, fmt='%.4f', delimiter=";")


def classify(workspace, filename, model, features_file):
    dictio = load_features(workspace + "features/" + filename[0:-4] + "_features.sbf", features_file)
    # Normalize by (0,1) and replace nan by -1
    data = MinMaxScaler((0, 1)).fit_transform(dictio['features'])
    data = np.nan_to_num(data, nan=-1)

    labels_pred = model.predict(data)
    confid_pred = model.predict_proba(data)
    confid_pred = np.max(confid_pred, axis=1)
    lasdata = las.read(workspace + filename)

    lasdata.classification = labels_pred
    # print(np.shape(lasdata))
    # print(np.shape(data))
    extra = [(("ind_confid", "float32"), np.round(confid_pred * 100, decimals=1))]
    las.WriteLAS(workspace + filename[0:-4] + "_class.laz", lasdata, format_id=1, extra_fields=extra)


def cross_validation(model, cv, X, y_true):
    scores1 = dict(zip(list(np.unique(y_true)) + ['all'], [[] for i in range(0,len(np.unique(y_true)) + 1)]))
    scores2 = dict(zip(list(np.unique(y_true)) + ['all'], [[] for i in range(0,len(np.unique(y_true)) + 1)]))
    feat_import = []
    count = 1
    print("Cross Validation test with %i folds:" %cv.get_n_splits())
    for train_idx,test_idx in cv.split(X,y_true):
        print(str(count) + "...", end="\r")
        count += 1
        model.fit(X[train_idx,:], y_true[train_idx])
        y_pred = model.predict(X[test_idx, :])
        scores1['all'] += [metrics.cohen_kappa_score(y_pred,y_true[test_idx])]
        scores2['all'] += [metrics.accuracy_score(y_true[test_idx], y_pred)]
        feat_import += [model.feature_importances_ * 100]
        for label in np.unique(y_true):
            scores1[label] += [metrics.cohen_kappa_score(y_pred == label, y_true[test_idx] == label)]
            scores2[label] += [metrics.accuracy_score(y_true[test_idx] == label, y_pred == label)]
    print("done!")
    return scores1, scores2, np.mean(feat_import, axis=0)
