import sqlite3
import pandas as pd
import argparse

def analyze_bluecoins_db(db_path):
    try:
        # 連接至 SQLite 資料庫
        conn = sqlite3.connect(db_path)

        # 設定 Pandas 顯示選項，確保中文字元（CJK）對齊與排版正確
        pd.set_option('display.unicode.east_asian_width', True)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.max_colwidth', 20)
        pd.set_option('display.expand_frame_repr', True)  # 超出寬度時自動折行
        pd.set_option('display.width', 120)

        print("\n" + "="*40)
        print("  BLUECOINS 帳戶清單 (Account Name)")
        print("="*40)
        acc_cols = pd.read_sql_query("PRAGMA table_info(ACCOUNTSTABLE);", conn)['name'].tolist()
        at_cols = pd.read_sql_query("PRAGMA table_info(ACCOUNTTYPETABLE);", conn)['name'].tolist()
        ag_cols = pd.read_sql_query("PRAGMA table_info(ACCOUNTINGGROUPTABLE);", conn)['name'].tolist()

        # 更強大的自動偵測邏輯：尋找名稱中包含 'Name' 的欄位，若無則尋找不含 'ID' 的描述欄位
        def find_name_col(cols, default):
            return next((c for c in cols if 'Name' in c), 
                        next((c for c in cols if 'ID' not in c and 'Table' not in c), default))

        acc_name_col = find_name_col(acc_cols, 'accountName')
        at_name_col = find_name_col(at_cols, 'accountTypeName')
        ag_name_col = find_name_col(ag_cols, 'accountingGroupName')

        # 取得關聯 ID 欄位 (分別偵測各表中的實際欄位名)
        at_pk = 'accountTypeTableID' if 'accountTypeTableID' in at_cols else 'accountTypeID'
        at_fk = 'accountTypeID' if 'accountTypeID' in acc_cols else 'accountTypeTableID'
        acc_pk = 'accountsTableID' if 'accountsTableID' in acc_cols else 'accountTableID'
        
        ag_pk = 'accountingGroupTableID' if 'accountingGroupTableID' in ag_cols else 'accountingGroupID'
        ag_fk = 'accountingGroupTableID' if 'accountingGroupTableID' in at_cols else 'accountingGroupID'

        # 偵測隱藏狀態欄位
        is_hidden_expr = 'a.accountHidden' if 'accountHidden' in acc_cols else '0'

        # 取得交易表欄位以偵測刪除標記
        trans_cols = pd.read_sql_query("PRAGMA table_info(TRANSACTIONSTABLE);", conn)['name'].tolist()
        is_deleted_tx_expr = 't.deletedTransaction' if 'deletedTransaction' in trans_cols else '0'

        # 執行三表關聯查詢：帳戶 -> 帳戶類型 -> 會計群組
        account_query = f"""
            SELECT 
                ag.{ag_name_col} as ag_name,
                at.{at_name_col} as at_name,
                a.{acc_name_col} as acc_name,
                {is_hidden_expr} as is_hidden
            FROM ACCOUNTSTABLE as a
            JOIN ACCOUNTTYPETABLE as at ON a.{at_fk} = at.{at_pk}
            JOIN ACCOUNTINGGROUPTABLE as ag ON at.{ag_fk} = ag.{ag_pk}
            ORDER BY ag.{ag_pk} ASC, at.{at_pk} ASC, a.{acc_name_col} ASC;
        """
        accounts = pd.read_sql_query(account_query, conn)
        
        current_ag = ""
        current_at = ""
        for _, row in accounts.iterrows():
            if row['ag_name'] != current_ag:
                current_ag = row['ag_name']
                print(f"\n【{current_ag}】")
            if row['at_name'] != current_at:
                current_at = row['at_name']
                print(f"  └─ [{current_at}]")
            
            status = " (隱藏)" if row['is_hidden'] == 1 else ""
            print(f"      • {row['acc_name']}{status}")

        print("\n" + "="*40)
        print("  BLUECOINS 帳戶原始數據分析 (Raw Account Data)")
        print("="*40)
        # 取得帳戶表的原始欄位資訊
        # 包含：貨幣、隱藏狀態、淨值計算標記、信用額度以及動態計算的餘額
        # 注意：Bluecoins 的餘額是所有交易的加總
        acc_raw_query = f"""
            SELECT 
                a.{acc_pk} as "ID",
                a.{acc_name_col} as "Name",
                a.accountCurrency as "Cur",
                (SELECT SUM(t.amount) / 1000000.0 
                 FROM TRANSACTIONSTABLE t 
                 WHERE t.accountID = a.{acc_pk} AND {is_deleted_tx_expr.replace('t.', 't.')} != 5
                ) as "Balance",
                a.accountHidden as "Hide",
                a.cashBasedAccounts as "NetWorth",
                a.accountSelectorVisibility as "Select",
                a.creditLimit / 1000000.0 as "Limit",
                a.accountsExtraColumnInt1 as "ExInt1",
                a.accountsExtraColumnInt2 as "ExInt2"
            FROM ACCOUNTSTABLE as a
            ORDER BY a.accountHidden ASC, a.{acc_name_col} ASC;
        """
        df_acc_raw = pd.read_sql_query(acc_raw_query, conn).fillna(0)
        
        if df_acc_raw.empty:
            print("  (未在資料庫中找到帳戶數據)")
        else:
            # 格式化顯示：ID 靠左，其餘欄位適度留白
            print(df_acc_raw.to_string(index=False, justify='left', col_space=8))
            print("\n  [欄位說明]:")
            print("  - NetWorth: 1=計入淨值/報表, 0=排除")
            print("  - Select: 1=顯示在選單, 0=隱藏")
            print("  - ExInt1/2: 某些版本用來儲存初始餘額或特定屬性")

        print("\n" + "="*40)
        print("  BLUECOINS 類別清單 (Parent > Child)")
        print("="*40)
        child_cols = pd.read_sql_query("PRAGMA table_info(CHILDCATEGORYTABLE);", conn)['name'].tolist()
        parent_cols = pd.read_sql_query("PRAGMA table_info(PARENTCATEGORYTABLE);", conn)['name'].tolist()
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)['name'].tolist()

        # 使用 find_name_col 偵測類別名稱欄位
        c_name_col = find_name_col(child_cols, 'childCategoryName')
        p_name_col = find_name_col(parent_cols, 'parentCategoryName')

        # 尋找用於 Join 的 ID 欄位 (主鍵 PK 與外鍵 FK)
        # 最可靠的方法：尋找兩個表共同擁有的 ID 欄位
        common_id_cols = [c for c in child_cols if c in parent_cols and 'ID' in c]
        
        # 偵測交易類型欄位 (通常在父類別表)
        type_col = next((c for c in parent_cols if 'transactionType' in c or 'typeID' in c), None)
        
        join_group_sql = ""
        type_select = ""

        if type_col:
            type_select = f"p.{type_col}"
        elif 'CATEGORYGROUPTABLE' in tables:
            cg_cols = pd.read_sql_query("PRAGMA table_info(CATEGORYGROUPTABLE);", conn)['name'].tolist()
            cg_type_col = next((c for c in cg_cols if 'transactionType' in c or 'typeID' in c), None)
            cg_id_col = next((c for c in cg_cols if 'categoryGroupTableID' in c or 'categoryGroupID' in c), None)
            p_cg_id_col = next((c for c in parent_cols if 'categoryGroupTableID' in c or 'categoryGroupID' in c), None)
            cg_name_col = next((c for c in cg_cols if 'categoryGroupName' in c or 'groupName' in c or 'Name' in c), None)
            
            if cg_id_col and p_cg_id_col:
                join_group_sql = f"LEFT JOIN CATEGORYGROUPTABLE as cg ON p.{p_cg_id_col} = cg.{cg_id_col}"
                if cg_type_col:
                    type_select = f"cg.{cg_type_col}"
                elif cg_id_col:
                    # 直接使用群組表的 ID 作為類型標籤，避免名稱對應錯誤
                    type_select = f"cg.{cg_id_col}"

        if not type_select:
            type_select = "0"

        has_type = type_select != "0"

        if common_id_cols:
            p_pk = c_fk = common_id_cols[0]
        else:
            # 備援方案：嘗試常見的候選名單
            id_candidates = ['parentCategoryTableID', 'categoryGroupTableID', 'categoryGroupID', 'parentCategoryID']
            p_pk = next((c for c in id_candidates if c in parent_cols), 'parentCategoryTableID')
            c_fk = next((c for c in id_candidates if c in child_cols), p_pk)

        # 決定排序條件：如果沒有交易類型欄位，就不執行類型排序
        cat_order_by = f"{type_select} ASC, " if has_type else ""

        # 尋找子類別的主鍵 ID 以辨識重複名稱
        c_pk = next((c for c in child_cols if 'ID' in c and 'parent' not in c.lower()), 'childCategoryTableID')

        # 偵測停用狀態欄位
        # 注意：您的版本可能使用 categorySelectorVisibility (1=顯示, 0=隱藏)
        if 'deletedCategory' in child_cols:
            is_deleted_expr_c = 'c.deletedCategory'
        else:
            is_deleted_expr_c = '0'

        is_deleted_expr_p = 'p.deletedCategory' if 'deletedCategory' in parent_cols else '0'

        categories = pd.read_sql_query(f"""
            SELECT 
                p.{p_name_col} as parent, 
                c.{c_name_col} as child,
                c.{c_pk} as child_id,
                {type_select} as tx_type,
                {is_deleted_expr_c} as is_deleted,
                {is_deleted_expr_p} as p_is_deleted
            FROM CHILDCATEGORYTABLE as c 
            JOIN PARENTCATEGORYTABLE as p ON c.{c_fk} = p.{p_pk} 
            {join_group_sql}
            ORDER BY {cat_order_by} p.{p_name_col} ASC, c.{c_name_col} ASC;
        """, conn)

        current_parent = ""
        current_type = -1
        # 根據資料庫實測：2=收入, 3=支出, 1=轉帳
        type_titles = {2: "收入", 3: "支出", 1: "轉帳"}

        for _, row in categories.iterrows():
            # 檢查交易類型是否變更 (收入/支出/轉帳)
            if row['tx_type'] != current_type:
                current_type = row['tx_type']
                type_name = type_titles.get(current_type, "其他/未知")
                print(f"\n【{type_name}】")
                current_parent = ""  # 換類型時，重置大類別追蹤

            # 檢查大類別是否變更
            parent_display = row['parent']
            if parent_display != current_parent:
                current_parent = parent_display
                p_status = " (停用)" if row['p_is_deleted'] == 1 else ""
                print(f"  └─ [{current_parent}]{p_status}")
            
            c_status = " (停用)" if row['is_deleted'] == 1 else ""
            print(f"      • {row['child']} [ID: {row['child_id']}]{c_status}")

        print("\n" + "="*40)
        print("  交易紀錄原始數據分析 (Raw Database Data)")
        print("="*40)
        # 取得 Payee (Item) 欄位名稱
        item_cols = pd.read_sql_query("PRAGMA table_info(ITEMTABLE);", conn)['name'].tolist()
        item_name_col = find_name_col(item_cols, 'itemName')
        # 取得標籤表資訊以修正標籤查詢 (避免抓到全資料庫標籤)
        label_cols = pd.read_sql_query("PRAGMA table_info(LABELSTABLE);", conn)['name'].tolist()
        l_name_col = find_name_col(label_cols, 'labelName')
        # 偵測標籤表中關聯交易的 ID 欄位 (可能是 transactionsTableID, transactionID 等)
        l_ref_col = next((c for c in label_cols if 'transactionsTableID' in c or 'transactionID' in c or 'transactionTableID' in c), None)
        label_subquery = f"(SELECT group_concat({l_name_col}, ' ') FROM LABELSTABLE WHERE LABELSTABLE.{l_ref_col} = t.transactionsTableID)" if l_ref_col else "''"

        # 獲取最新的 50 筆原始交易紀錄
        trans_raw_query = f"""
            SELECT 
                t.transactionsTableID as "TX_ID",
                t.date as "Date",
                it.{item_name_col} as "Item",
                p.{p_name_col} as "Parent",
                c.{c_name_col} as "Category",
                t.accountID as "Acc_ID",
                t.amount as "Raw_Amount",
                t.transactionCurrency as "Cur",
                t.transactionTypeID as "Type_ID",
                t.accountPairID as "Pair_ID",
                t.status as "Status",
                t.newSplitTransactionID as "Split_ID",
                t.notes as "Notes",
                {label_subquery} as "Labels",
                {is_deleted_tx_expr} as "Del"
            FROM TRANSACTIONSTABLE t
            LEFT JOIN ITEMTABLE it ON t.itemID = it.itemTableID
            LEFT JOIN CHILDCATEGORYTABLE c ON t.categoryID = c.{c_pk}
            LEFT JOIN PARENTCATEGORYTABLE p ON c.{c_fk} = p.{p_pk}
            WHERE {is_deleted_tx_expr} != 5
            ORDER BY t.date DESC, t.transactionsTableID DESC
            LIMIT 50;
        """
        df_raw = pd.read_sql_query(trans_raw_query, conn).fillna('')
        
        if df_raw.empty:
            print("  (未在資料庫中找到交易紀錄)")
        else:
            # 強制顯示所有欄位與原始數值，並增加欄位間距與左對齊
            print(df_raw.to_string(index=False, justify='left', col_space=12))

        print("\n" + "="*40)
        print("  BLUECOINS 交易紀錄 (Advanced Template 格式)")
        print("="*40)
        
        # 建立完整解析查詢
        # 欄位對照 Advanced Template:
        # (1)Type, (2)Date, (3)Item or Payee, (4)Amount, (5)Currency, (6)ConversionRate, 
        # (7)Parent Category, (8)Category, (9)Account Type, (10)Account, (11)Notes, (12) Label, (13) Status, (14) Split
        
        template_query = f"""
            SELECT 
                CASE t.transactionTypeID 
                    WHEN 1 THEN 't' 
                    WHEN 2 THEN 'i' 
                    WHEN 3 THEN 'e' 
                    WHEN 4 THEN (CASE WHEN t.amount > 0 THEN 'i' ELSE 'e' END)
                    ELSE 'e' END as "(1)Type",
                t.date as "(2)Date",
                it.{item_name_col} as "(3)Item or Payee",
                CASE 
                    WHEN t.transactionTypeID = 1 THEN (t.amount / 1000000.0) 
                    ELSE ABS(t.amount / 1000000.0) 
                END as "(4)Amount",
                t.transactionCurrency as "(5)Currency",
                t.conversionRateNew as "(6)ConversionRate",
                p.{p_name_col} as "(7)Parent Category",
                c.{c_name_col} as "(8)Category",
                at.{at_name_col} as "(9)Account Type",
                a.{acc_name_col} as "(10)Account",
                t.notes as "(11)Notes",
                {label_subquery} as "(12) Label",
                CASE t.status 
                    WHEN 1 THEN 'C' 
                    WHEN 2 THEN 'R' 
                    ELSE '' END as "(13) Status",
                CASE 
                    WHEN t.newSplitTransactionID != 0 THEN 's' 
                    ELSE '' END as "(14) Split"
            FROM TRANSACTIONSTABLE t
            LEFT JOIN ITEMTABLE it ON t.itemID = it.itemTableID
            LEFT JOIN CHILDCATEGORYTABLE c ON t.categoryID = c.{c_pk}
            LEFT JOIN PARENTCATEGORYTABLE p ON c.{c_fk} = p.{p_pk}
            LEFT JOIN ACCOUNTSTABLE a ON t.accountID = a.{acc_pk}
            LEFT JOIN ACCOUNTTYPETABLE at ON a.{at_fk} = at.{at_pk}
            WHERE {is_deleted_tx_expr} != 5
            ORDER BY t.date DESC
            LIMIT 50;
        """
        
        df_template = pd.read_sql_query(template_query, conn).fillna('')
        
        # 處理日期格式 (從 YYYY-MM-DD HH:MM:SS 轉為 M/D/YYYY)
        try:
            dt_series = pd.to_datetime(df_template['(2)Date'])
            # 平台無關的 M/D/YYYY 格式化，節省空間
            df_template['(2)Date'] = dt_series.apply(lambda x: f"{x.month}/{x.day}/{x.year}")
        except:
            pass # 若格式不合則保持原樣

        if df_template.empty:
            print("  (沒有找到交易紀錄)")
        else:
            # 取得標準字串表達形式
            res = df_template.to_string(index=False, justify='left', col_space=4)
            lines = res.split('\n')
            
            final_output = []
            new_block = True
            for line in lines:
                if not line.strip(): # 處理分段顯示的空行
                    final_output.append("")
                    new_block = True
                    continue
                
                final_output.append(line)
                if new_block:
                    final_output.append("=" * 120)
                    new_block = False
                else:
                    final_output.append("-" * 120)
            
            print("\n".join(final_output))

        print("\n" + "="*40)
        print("  查詢完成")
        print("="*40)

        conn.close()
    except Exception as e:
        print(f"解析失敗: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Bluecoins .fydb database.")
    parser.add_argument("-i", "--input", required=True, help="Path to the Bluecoins .fydb file")
    args = parser.parse_args()

    analyze_bluecoins_db(args.input)
